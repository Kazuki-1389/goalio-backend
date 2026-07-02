from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx

from app.schemas.matches import LineupPlayer, TeamLineup
from app.services.lineup_providers.base import MatchMeta, ProviderResult
from app.services.lineup_providers.thesportsdb import names_match


class FootballDataProvider:
    """football-data.org v4 fallback for match lineups.

    Match detail can contain confirmed ``lineup`` and ``bench`` arrays. List
    responses intentionally omit that deep data, so matching and detail fetches
    are separate requests.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.football-data.org/v4", timeout: float = 8.0):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch(self, meta: MatchMeta) -> ProviderResult:
        attempts: list[dict] = []
        if not self.api_key:
            return ProviderResult(attempts=[{"provider": "footballData", "step": "configuration", "success": False, "reason": "API key missing"}])
        if meta.kickoff is None:
            return ProviderResult(attempts=[{"provider": "footballData", "step": "match_lookup", "success": False, "reason": "kickoff unavailable"}])
        match_date = meta.kickoff.date()
        try:
            # A small UTC window handles provider date-boundary/indexing quirks.
            payload = self._get("/matches", {"dateFrom": (match_date - timedelta(days=1)).isoformat(), "dateTo": (match_date + timedelta(days=1)).isoformat()})
            matches = payload.get("matches") or []
            match = next((item for item in matches if _matches_meta(item, meta)), None)
            attempts.append({"provider": "footballData", "step": "match_lookup", "success": match is not None, "candidates": len(matches), "reason": None if match else "matching event not found"})
            if match is None:
                return ProviderResult(attempts=attempts)
            detail = self._get(f"/matches/{match['id']}")
            lineups = parse_match_lineup(detail, meta)
            attempts.append({"provider": "footballData", "step": "match_lineup", "success": _has_players(lineups), "providerEventId": str(match["id"]), "homeStarters": len(lineups[0].starters), "awayStarters": len(lineups[1].starters), "reason": None if _has_players(lineups) else "lineup not published"})
            if _has_players(lineups):
                return ProviderResult(lineups=lineups, attempts=attempts)
            rosters = self._fetch_rosters(detail, meta, attempts)
            return ProviderResult(lineups=rosters if _has_players(rosters) else [], attempts=attempts)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            attempts.append({"provider": "footballData", "step": "request", "success": False, "reason": str(exc)[:200]})
            return ProviderResult(attempts=attempts)

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        response = httpx.get(f"{self.base_url}{path}", params=params, headers={"X-Auth-Token": self.api_key}, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _fetch_rosters(self, match: dict[str, Any], meta: MatchMeta, attempts: list[dict]) -> list[TeamLineup]:
        result: list[TeamLineup] = []
        for side, name, team_id in (("homeTeam", meta.home_team, meta.home_team_id), ("awayTeam", meta.away_team, meta.away_team_id)):
            provider_team_id = (match.get(side) or {}).get("id")
            payload = self._get(f"/teams/{provider_team_id}") if provider_team_id is not None else {}
            squad = [_player(item, False) for item in payload.get("squad") or []]
            result.append(TeamLineup(teamId=team_id, teamName=name, coach=(payload.get("coach") or {}).get("name"), substitutes=squad))
        attempts.append({"provider": "footballData", "step": "team_squads", "success": _has_players(result), "homePlayers": len(result[0].substitutes), "awayPlayers": len(result[1].substitutes), "reason": None if _has_players(result) else "team squads unavailable"})
        return result


def parse_match_lineup(payload: dict[str, Any], meta: MatchMeta) -> list[TeamLineup]:
    result: list[TeamLineup] = []
    for side, name, team_id in (("homeTeam", meta.home_team, meta.home_team_id), ("awayTeam", meta.away_team, meta.away_team_id)):
        block = payload.get(side) or {}
        starters = [_player(item, True) for item in block.get("lineup") or []]
        bench = [_player(item, False) for item in block.get("bench") or []]
        result.append(TeamLineup(teamId=team_id, teamName=name, formation=block.get("formation"), coach=(block.get("coach") or {}).get("name"), starters=starters, substitutes=bench))
    return result


def _player(item: dict[str, Any], starter: bool) -> LineupPlayer:
    return LineupPlayer(id=str(item.get("id")) if item.get("id") is not None else None, name=str(item.get("name") or ""), position=item.get("position"), jersey=str(item.get("shirtNumber")) if item.get("shirtNumber") is not None else None, starter=starter, substitute=not starter, role="Starter" if starter else "Bench")


def _matches_meta(item: dict[str, Any], meta: MatchMeta) -> bool:
    home = (item.get("homeTeam") or {}).get("name") or (item.get("homeTeam") or {}).get("shortName") or ""
    away = (item.get("awayTeam") or {}).get("name") or (item.get("awayTeam") or {}).get("shortName") or ""
    return names_match(str(home), meta.home_team) and names_match(str(away), meta.away_team)


def _has_players(lineups: list[TeamLineup]) -> bool:
    return len(lineups) == 2 and any(team.starters or team.substitutes for team in lineups)
