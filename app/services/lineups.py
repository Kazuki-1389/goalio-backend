from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import re
from typing import Protocol
from urllib.parse import quote_plus

from fastapi import HTTPException
from google.cloud.firestore_v1 import Client

from app.schemas.lineups import (
    LineupManager,
    MatchLineupResponse,
    NormalizedLineupPlayer,
    NormalizedTeamLineup,
)
from app.schemas.matches import LineupPlayer, MatchDetail, MatchTeam, TeamLineup
from app.services.match_detail import EspnMatchDetailClient
from app.core.config import get_settings

logger = logging.getLogger(__name__)


FORMATION_COORDINATES = {
    "4-3-3": [(50, 92), (18, 74), (39, 74), (61, 74), (82, 74), (28, 55), (50, 55), (72, 55), (25, 34), (50, 34), (75, 34)],
    "4-2-3-1": [(50, 92), (18, 74), (39, 74), (61, 74), (82, 74), (38, 60), (62, 60), (25, 44), (50, 44), (75, 44), (50, 28)],
    "4-4-2": [(50, 92), (18, 74), (39, 74), (61, 74), (82, 74), (18, 55), (39, 55), (61, 55), (82, 55), (38, 34), (62, 34)],
    "3-5-2": [(50, 92), (28, 74), (50, 74), (72, 74), (12, 55), (32, 55), (50, 55), (68, 55), (88, 55), (38, 34), (62, 34)],
    "3-4-3": [(50, 92), (28, 74), (50, 74), (72, 74), (18, 55), (39, 55), (61, 55), (82, 55), (25, 34), (50, 34), (75, 34)],
    "4-1-4-1": [(50, 92), (18, 74), (39, 74), (61, 74), (82, 74), (50, 62), (18, 48), (39, 48), (61, 48), (82, 48), (50, 30)],
    "5-3-2": [(50, 92), (12, 74), (32, 74), (50, 74), (68, 74), (88, 74), (28, 55), (50, 55), (72, 55), (38, 34), (62, 34)],
}


@dataclass
class CachedLineup:
    response: MatchLineupResponse
    content_hash: str | None = None


@dataclass(frozen=True)
class LineupSourceResolver:
    event_id: str
    home_team: str
    away_team: str
    league: str

    def resolve(self) -> dict[str, str]:
        query = f"{self.home_team} vs {self.away_team} lineups football"
        yahoo_query = f"site:sports.yahoo.com {self.home_team} vs {self.away_team} lineups"
        return {
            "espnSummaryUrl": f"https://site.api.espn.com/apis/site/v2/sports/soccer/{self.league}/summary?event={quote_plus(self.event_id)}",
            "googleSearchUrl": f"https://www.google.com/search?q={quote_plus(query)}",
            "googleSportsUrl": "",
            "yahooSearchUrl": f"https://search.yahoo.com/search?p={quote_plus(yahoo_query)}",
            "yahooMatchUrl": "",
        }


class LineupStore(Protocol):
    def get(self, event_id: str) -> CachedLineup | None: ...

    def write(self, response: MatchLineupResponse, attempts: dict[str, dict], content_hash: str) -> None: ...


class FirestoreLineupStore:
    def __init__(self, client: Client):
        self.client = client

    def _ref(self, event_id: str):
        return self.client.collection("matches").document(event_id).collection("lineups").document("current")

    def get(self, event_id: str) -> CachedLineup | None:
        snapshot = self._ref(event_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        public = {key: value for key, value in data.items() if not key.startswith("_") and key not in {"fetchAttempts", "lastFetchedAt"}}
        try:
            return CachedLineup(MatchLineupResponse(**public), data.get("_contentHash"))
        except (TypeError, ValueError):
            return None

    def write(self, response: MatchLineupResponse, attempts: dict[str, dict], content_hash: str) -> None:
        payload = response.model_dump(mode="json", exclude={"fetchAttempts"})
        self._ref(response.eventId).set(
            {
                **payload,
                "lastFetchedAt": int(datetime.now(timezone.utc).timestamp() * 1000),
                "fetchAttempts": attempts,
                "_contentHash": content_hash,
            }
        )


class LineupService:
    def __init__(self, client: EspnMatchDetailClient, store: LineupStore):
        self.client = client
        self.store = store

    def get(self, league: str, event_id: str, force: bool = False) -> MatchLineupResponse:
        now = datetime.now(timezone.utc)
        cached = self.store.get(event_id)
        if cached and not force and _cache_is_fresh(cached.response, now):
            return cached.response

        attempts = {name: {"status": "skipped", "url": None, "reason": None, "rawFound": False} for name in ("espn", "google", "yahoo")}
        try:
            detail = self.client.espn_detail(league, event_id)
        except (HTTPException, Exception):
            attempts["espn"].update(status="failed_error", reason="summary request failed")
            if cached:
                return cached.response.model_copy(update={"source": "cache", "isStale": True})
            return _empty_response(event_id, now)

        kickoff = _parse_datetime(detail.kickoff)
        resolved = LineupSourceResolver(
            event_id, detail.homeTeam.shortName or detail.homeTeam.name if detail.homeTeam else "home",
            detail.awayTeam.shortName or detail.awayTeam.name if detail.awayTeam else "away", league,
        ).resolve()
        attempts["espn"]["url"] = resolved["espnSummaryUrl"]
        attempts["google"]["url"] = resolved["googleSearchUrl"]
        attempts["yahoo"]["url"] = resolved["yahooSearchUrl"]
        final = _is_final(detail)
        within_scrape_window = kickoff is None or kickoff - now <= timedelta(hours=24)
        lineups = detail.lineups if _has_starting_lineup(detail.lineups) else []
        source = "espn"
        if not lineups:
            try:
                lineups = self.client.espn_lineups(league, event_id)
                attempts["espn"].update(status="success" if _has_starting_lineup(lineups) else "failed_no_lineups", rawFound=bool(lineups))
            except Exception:
                attempts["espn"].update(status="failed_error", reason="ESPN lineup fetch failed")
                lineups = []
        else:
            attempts["espn"].update(status="success", rawFound=True)

        if not _has_starting_lineup(lineups) and within_scrape_window and (not final or cached is None):
            attempts["google"].update(status="failed_no_lineups")
            try:
                lineups = self.client.google_lineups(league, event_id, detail)
                if _has_starting_lineup(lineups):
                    attempts["google"].update(status="success", rawFound=True)
                    source = "google"
            except Exception:
                attempts["google"].update(status="failed_error", reason="Google fetch or parse failed")
                lineups = []

        if not _has_starting_lineup(lineups) and within_scrape_window and (not final or cached is None):
            attempts["yahoo"].update(status="failed_no_lineups")
            try:
                lineups = self.client.yahoo_lineups(league, event_id, detail)
                if _has_starting_lineup(lineups):
                    attempts["yahoo"].update(status="success", rawFound=True)
                    source = "yahoo"
            except Exception:
                attempts["yahoo"].update(status="failed_error", reason="Yahoo discovery, fetch, or parse failed")
                lineups = []

        if not _has_starting_lineup(lineups) and cached and _response_has_players(cached.response):
            return cached.response.model_copy(update={"source": "cache", "isStale": True})

        response = _normalize_response(event_id, detail, lineups, source if _has_starting_lineup(lineups) else "generated", now)
        if get_settings().lineup_debug:
            response.fetchAttempts = attempts
        if not _response_has_players(response):
            logger.warning("LINEUP_EMPTY eventId=%s espn=%s google=%s yahoo=%s cache=%s returning=generated_not_available", event_id, attempts["espn"]["status"], attempts["google"]["status"], attempts["yahoo"]["status"], "present" if cached else "empty")
        content_hash = _content_hash(response)
        if cached is None or cached.content_hash != content_hash or _refresh_changed(cached.response, response):
            self.store.write(response, attempts, content_hash)
        return response


def _normalize_response(
    event_id: str,
    detail: MatchDetail,
    lineups: list[TeamLineup],
    source: str,
    now: datetime,
) -> MatchLineupResponse:
    home_raw = _find_team_lineup(lineups, detail.homeTeam)
    away_raw = _find_team_lineup(lineups, detail.awayTeam)
    home, home_estimated = _normalize_team(home_raw, detail.homeTeam, mirror=False)
    away, away_estimated = _normalize_team(away_raw, detail.awayTeam, mirror=True)
    has_players = bool(home.startingXI or away.startingXI)
    final = _is_final(detail)
    live = _is_live(detail)
    both_teams = bool(home.startingXI and away.startingXI)
    status = "FINAL" if final and both_teams else "LIVE" if live and both_teams else "CONFIRMED" if both_teams else "PARTIAL" if has_players else "NOT_AVAILABLE"
    formation_status = "ESTIMATED" if has_players and (home_estimated or away_estimated) else "CONFIRMED" if has_players else "UNKNOWN"
    kickoff = _parse_datetime(detail.kickoff)
    return MatchLineupResponse(
        eventId=event_id,
        status=status,
        source=source,
        formationStatus=formation_status,
        lastUpdated=now,
        nextRefreshAt=_next_refresh(now, kickoff, final),
        kickoff=kickoff,
        home=home,
        away=away,
    )


def _empty_response(event_id: str, now: datetime) -> MatchLineupResponse:
    return MatchLineupResponse(
        eventId=event_id,
        status="NOT_AVAILABLE",
        source="generated",
        formationStatus="UNKNOWN",
        lastUpdated=now,
        nextRefreshAt=now + timedelta(minutes=5),
        home=NormalizedTeamLineup(),
        away=NormalizedTeamLineup(),
    )


def _normalize_team(raw: TeamLineup | None, team: MatchTeam | None, mirror: bool) -> tuple[NormalizedTeamLineup, bool]:
    raw_starters = _dedupe_players(raw.starters if raw else [])
    raw_bench = _dedupe_players(raw.substitutes if raw else [])
    starters = raw_starters[:11]
    overflow = raw_starters[11:]
    starter_keys = {_player_key(player) for player in starters}
    bench = [player for player in overflow + raw_bench if _player_key(player) not in starter_keys]
    formation = _canonical_formation(raw.formation if raw else None)
    estimated = False
    if starters and formation not in FORMATION_COORDINATES:
        formation = _infer_formation(starters) or "4-3-3"
        estimated = True
    ordered = sorted(starters, key=_position_rank)
    coordinates = FORMATION_COORDINATES.get(formation or "", [])
    normalized_starters = [
        _normalized_player(player, coordinates[index] if index < len(coordinates) else None, mirror)
        for index, player in enumerate(ordered)
    ]
    normalized_bench = [_normalized_player(player, None, mirror=False) for player in _dedupe_players(bench)]
    return NormalizedTeamLineup(
        teamId=team.id if team else raw.teamId if raw else None,
        teamName=(team.shortName or team.name) if team else raw.teamName if raw else None,
        teamLogo=team.logo if team else None,
        formation=formation,
        manager=LineupManager(name=raw.coach) if raw and raw.coach else None,
        startingXI=normalized_starters,
        bench=normalized_bench,
        unavailable=[],
    ), estimated


def _normalized_player(player: LineupPlayer, generated: tuple[int, int] | None, mirror: bool) -> NormalizedLineupPlayer:
    has_coordinates = player.x is not None and player.y is not None
    x, y = (player.x, player.y) if has_coordinates else generated if generated is not None else (None, None)
    if y is not None and mirror and not has_coordinates:
        y = 100 - y
    return NormalizedLineupPlayer(
        id=player.id,
        name=player.name.strip(),
        number=_number(player.jersey),
        position=player.position,
        role=player.role or _role(player.position),
        photo=player.photo,
        captain=player.captain,
        x=x,
        y=y,
    )


def _find_team_lineup(lineups: list[TeamLineup], team: MatchTeam | None) -> TeamLineup | None:
    if team is None:
        return None
    return next((lineup for lineup in lineups if lineup.teamId == team.id), None) or next(
        (lineup for lineup in lineups if lineup.teamName and lineup.teamName.casefold() in {team.name.casefold(), (team.shortName or "").casefold()}),
        None,
    )


def _dedupe_players(players: list[LineupPlayer]) -> list[LineupPlayer]:
    result = []
    seen = set()
    for player in players:
        if not player.name.strip():
            continue
        key = _player_key(player)
        if key in seen:
            continue
        seen.add(key)
        result.append(player)
    return result


def _player_key(player: LineupPlayer) -> str:
    return player.id or re.sub(r"\W+", "", player.name.casefold())


def _position_rank(player: LineupPlayer) -> tuple[int, str]:
    position = (player.position or "").upper()
    rank = 0 if "GK" in position or "GOAL" in position else 1 if any(item in position for item in ("DEF", "CB", "LB", "RB", "WB")) else 2 if any(item in position for item in ("MID", "CM", "DM", "AM", "MF")) else 3
    return rank, player.formationPlace or player.name


def _infer_formation(players: list[LineupPlayer]) -> str | None:
    counts = [0, 0, 0]
    for player in players:
        rank = _position_rank(player)[0]
        if rank in (1, 2, 3):
            counts[rank - 1] += 1
    candidate = "-".join(str(value) for value in counts)
    return candidate if candidate in FORMATION_COORDINATES else None


def _canonical_formation(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.findall(r"\d", value)
    candidate = "-".join(digits)
    return candidate if candidate in FORMATION_COORDINATES else None


def _role(position: str | None) -> str | None:
    rank = _position_rank(LineupPlayer(name="Player", position=position))[0]
    return ("Goalkeeper", "Defender", "Midfielder", "Forward")[rank]


def _number(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


def _has_starting_lineup(lineups: list[TeamLineup]) -> bool:
    return any(lineup.starters for lineup in lineups)


def _response_has_players(response: MatchLineupResponse) -> bool:
    return bool(response.home.startingXI or response.away.startingXI)


def _is_live(detail: MatchDetail) -> bool:
    value = f"{detail.status or ''} {detail.statusDescription or ''}".casefold()
    return "live" in value or "half" in value or bool(re.search(r"\b\d{1,3}(?:\+\d+)?['’]", value))


def _is_final(detail: MatchDetail) -> bool:
    value = f"{detail.status or ''} {detail.statusDescription or ''}".casefold()
    return any(item in value for item in ("full time", "final", "ft", "aet", "pens"))


def _next_refresh(now: datetime, kickoff: datetime | None, final: bool) -> datetime | None:
    if final:
        return None
    if kickoff is None:
        return now + timedelta(minutes=30)
    remaining = kickoff - now
    if remaining > timedelta(hours=24):
        return kickoff - timedelta(hours=24)
    if remaining > timedelta(hours=2):
        return now + timedelta(minutes=30)
    return now + timedelta(minutes=5)


def _cache_is_fresh(response: MatchLineupResponse, now: datetime) -> bool:
    return response.status == "FINAL" or response.nextRefreshAt is None or response.nextRefreshAt > now


def _refresh_changed(old: MatchLineupResponse, new: MatchLineupResponse) -> bool:
    if old.nextRefreshAt is None or new.nextRefreshAt is None:
        return old.nextRefreshAt != new.nextRefreshAt
    return abs((old.nextRefreshAt - new.nextRefreshAt).total_seconds()) >= 60


def _content_hash(response: MatchLineupResponse) -> str:
    payload = response.model_dump(mode="json", exclude={"lastUpdated", "nextRefreshAt", "isStale"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
