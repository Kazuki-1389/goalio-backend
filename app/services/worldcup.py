from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from typing import Any

from app.schemas.matches import ScoreboardMatch, StandingTeam
from app.schemas.worldcup import (
    WorldCupBootstrap,
    WorldCupBracket,
    WorldCupBracketMatch,
    WorldCupFact,
    WorldCupGroup,
    WorldCupLibraryItem,
    WorldCupNextMatchSlot,
    WorldCupTournament,
)
from app.services.match_detail import EspnMatchDetailClient


WORLD_CUP_LEAGUE = "fifa.world"
WORLD_CUP_FINAL = date(2026, 7, 19)

ROUND_MATCH_ORDER = {
    "R32": [74, 77, 73, 75, 83, 84, 81, 82, 76, 78, 79, 80, 86, 88, 85, 87],
    "R16": [89, 90, 93, 94, 91, 92, 95, 96],
    "QF": [97, 98, 99, 100],
    "SF": [101, 102],
    "FINAL": [104],
}
ROUND_CODES = ("R32", "R16", "QF", "SF", "FINAL")
ROUND_SLOT_COUNTS = {"R32": 16, "R16": 8, "QF": 4, "SF": 2, "FINAL": 1}
NEXT_ROUND = {"R32": "R16", "R16": "QF", "QF": "SF", "SF": "FINAL"}


LIBRARY_ITEMS = [
    WorldCupLibraryItem(
        id="pele-legacy",
        title="The Legacy of Pele",
        category="History",
        body="The only player to win three FIFA World Cups became the tournament's enduring icon.",
        readMinutes=12,
    ),
    WorldCupLibraryItem(
        id="host-cities-2026",
        title="2026 Host Cities",
        category="Guide",
        body="The 2026 edition is staged across 16 cities in Canada, Mexico, and the United States.",
        readMinutes=6,
    ),
    WorldCupLibraryItem(
        id="knockout-format-2026",
        title="Round of 32 Explained",
        category="Format",
        body="The expanded 48-team format sends 32 teams into a single-elimination knockout path.",
        readMinutes=4,
    ),
]

FACTS = [
    WorldCupFact(title="Most titles", body="Brazil have won the men's FIFA World Cup five times."),
    WorldCupFact(title="2026 hosts", body="Canada, Mexico, and the United States co-host the 2026 tournament."),
    WorldCupFact(title="Expanded field", body="The 2026 World Cup is the first men's edition planned for 48 teams."),
]


class WorldCupService:
    def __init__(self, match_client: EspnMatchDetailClient):
        self.match_client = match_client

    def bootstrap(self, today: date | None = None) -> WorldCupBootstrap:
        current_date = today or date.today()
        schedule = self.match_client.schedule(
            WORLD_CUP_LEAGUE,
            date=None,
            from_date=(current_date - timedelta(days=7)).isoformat(),
            to_date=(current_date + timedelta(days=21)).isoformat(),
        )
        matches = schedule.matches
        live = [match for match in matches if match.state == "in"][:3]
        today_matches = [match for match in matches if _match_date(match) == current_date][:6]
        upcoming = [match for match in matches if match.state == "pre"][:6]
        recent = [match for match in matches if match.state == "post"][:6]
        standings = self.match_client.standings(WORLD_CUP_LEAGUE)
        groups = _groups(standings.teams)
        return WorldCupBootstrap(
            tournament=WorldCupTournament(
                id="worldcup-2026",
                name="FIFA World Cup 2026",
                stage=_stage_for_date(current_date),
                hostCities=16,
                daysToFinal=max(0, (WORLD_CUP_FINAL - current_date).days),
                lastSyncedAt=datetime.now(timezone.utc).isoformat(),
            ),
            liveMatches=live,
            todayMatches=today_matches,
            upcomingMatches=upcoming,
            recentResults=recent,
            groups=groups[:12],
            bracket=_bracket(matches),
            library=LIBRARY_ITEMS,
            randomFact=FACTS[current_date.toordinal() % len(FACTS)],
        )

    def groups(self) -> list[WorldCupGroup]:
        return _groups(self.match_client.standings(WORLD_CUP_LEAGUE).teams)

    def bracket(self) -> WorldCupBracket:
        current_date = date.today()
        schedule = self.match_client.schedule(
            WORLD_CUP_LEAGUE,
            date=None,
            from_date=(current_date - timedelta(days=7)).isoformat(),
            to_date=(current_date + timedelta(days=21)).isoformat(),
        )
        return _bracket(schedule.matches)

    def library(self) -> list[WorldCupLibraryItem]:
        return LIBRARY_ITEMS


def _groups(teams: list[StandingTeam]) -> list[WorldCupGroup]:
    buckets: dict[str, list[StandingTeam]] = {}
    for team in teams:
        code = (team.group or "Table").replace("Group ", "").strip() or "Table"
        buckets.setdefault(code, []).append(team)
    return [
        WorldCupGroup(code=code, teams=sorted(items, key=lambda item: item.rank or 999))
        for code, items in sorted(buckets.items())
    ]


def _bracket(matches: list[ScoreboardMatch]) -> WorldCupBracket:
    candidates: dict[str, list[tuple[ScoreboardMatch, int | None]]] = {code: [] for code in ROUND_CODES}
    seen_events: set[str] = set()
    for match in matches:
        if match.matchId in seen_events:
            continue
        seen_events.add(match.matchId)
        match_number = _match_number(match)
        round_code = _round_code(match, match_number)
        if round_code is not None:
            candidates[round_code].append((match, match_number))

    normalized: dict[str, list[WorldCupBracketMatch]] = {}
    for round_code in ROUND_CODES:
        slot_count = ROUND_SLOT_COUNTS[round_code]
        slots: list[WorldCupBracketMatch | None] = [None] * slot_count
        unslotted: list[ScoreboardMatch] = []
        number_slots = {number: index for index, number in enumerate(ROUND_MATCH_ORDER[round_code])}

        for match, match_number in sorted(candidates[round_code], key=lambda item: _candidate_sort_key(item[0])):
            slot_index = number_slots.get(match_number) if match_number is not None else None
            if slot_index is None:
                unslotted.append(match)
                continue
            if slots[slot_index] is not None:
                continue
            slots[slot_index] = _normalized_match(match, round_code, slot_index)

        remaining = iter(sorted(unslotted, key=_candidate_sort_key))
        for slot_index in range(slot_count):
            if slots[slot_index] is None:
                match = next(remaining, None)
                slots[slot_index] = (
                    _normalized_match(match, round_code, slot_index)
                    if match is not None
                    else _placeholder_match(round_code, slot_index)
                )
        normalized[round_code] = [slot for slot in slots if slot is not None]

    return WorldCupBracket(
        tournament="FIFA World Cup",
        bracketType="32_TEAM_KNOCKOUT",
        rounds=normalized,
    )


def _normalized_match(match: ScoreboardMatch, round_code: str, slot_index: int) -> WorldCupBracketMatch:
    return WorldCupBracketMatch(
        eventId=match.matchId,
        round=round_code,
        slotIndex=slot_index,
        status=match.status or match.statusDescription,
        homeTeam=_normalized_team_name(_team_name(match.homeTeam)),
        awayTeam=_normalized_team_name(_team_name(match.awayTeam)),
        homeLogo=match.homeTeam.logo if match.homeTeam else None,
        awayLogo=match.awayTeam.logo if match.awayTeam else None,
        homeScore=match.homeTeam.score if match.homeTeam else None,
        awayScore=match.awayTeam.score if match.awayTeam else None,
        winnerTeamId=_winner(match),
        kickoff=match.kickoff,
        nextMatchSlot=_next_match_slot(round_code, slot_index),
    )


def _placeholder_match(round_code: str, slot_index: int) -> WorldCupBracketMatch:
    source_round = {"R16": "R32", "QF": "R16", "SF": "QF", "FINAL": "SF"}.get(round_code)
    if source_round is None:
        home_team = away_team = "TBD"
    else:
        home_team = f"Winner of {source_round} Match {slot_index * 2 + 1}"
        away_team = f"Winner of {source_round} Match {slot_index * 2 + 2}"
    return WorldCupBracketMatch(
        eventId=f"wc2026-{round_code.lower()}-{slot_index}",
        round=round_code,
        slotIndex=slot_index,
        homeTeam=home_team,
        awayTeam=away_team,
        status="TBD",
        nextMatchSlot=_next_match_slot(round_code, slot_index),
    )


def _next_match_slot(round_code: str, slot_index: int) -> WorldCupNextMatchSlot | None:
    next_round = NEXT_ROUND.get(round_code)
    if next_round is None:
        return None
    return WorldCupNextMatchSlot(
        round=next_round,
        slotIndex=slot_index // 2,
        teamPosition="home" if slot_index % 2 == 0 else "away",
    )


def _round_code(match: ScoreboardMatch, match_number: int | None) -> str | None:
    if match_number is not None:
        for round_code, numbers in ROUND_MATCH_ORDER.items():
            if match_number in numbers:
                return round_code

    placeholder_round = _placeholder_target_round(_team_name(match.homeTeam), _team_name(match.awayTeam))
    if placeholder_round is not None:
        return placeholder_round

    joined = " ".join(value or "" for value in (match.statusDescription, match.name, match.shortName)).casefold()
    if "round of 32" in joined or re.search(r"\br32\b", joined):
        return "R32"
    if "round of 16" in joined or re.search(r"\br16\b", joined):
        return "R16"
    if "quarter" in joined or re.search(r"\bqf\b", joined):
        return "QF"
    if "semi" in joined or re.search(r"\bsf\b", joined):
        return "SF"
    if "third place" in joined:
        return None
    if "final" in joined:
        return "FINAL"

    parsed = _parse_date(match.kickoff)
    if parsed is None:
        return None
    if date(2026, 6, 28) <= parsed <= date(2026, 7, 3):
        return "R32"
    if date(2026, 7, 4) <= parsed <= date(2026, 7, 7):
        return "R16"
    if date(2026, 7, 9) <= parsed <= date(2026, 7, 11):
        return "QF"
    if date(2026, 7, 14) <= parsed <= date(2026, 7, 15):
        return "SF"
    if parsed == WORLD_CUP_FINAL:
        return "FINAL"
    return None


def _placeholder_target_round(*team_names: str | None) -> str | None:
    joined = " ".join(name or "" for name in team_names).upper()
    checks = (
        (r"(?:RD?32|R32)\s*W|WINNER\s+OF\s+R32", "R16"),
        (r"(?:RD?16|R16)\s*W|WINNER\s+OF\s+R16", "QF"),
        (r"QF\s*W|WINNER\s+OF\s+QF", "SF"),
        (r"SF\s*W|WINNER\s+OF\s+SF", "FINAL"),
    )
    return next((round_code for pattern, round_code in checks if re.search(pattern, joined)), None)


def _normalized_team_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    replacements = ((r"RD?32\s*W\s*(\d+)", "R32"), (r"RD?16\s*W\s*(\d+)", "R16"), (r"QF\s*W\s*(\d+)", "QF"), (r"SF\s*W\s*(\d+)", "SF"))
    for pattern, source_round in replacements:
        matched = re.fullmatch(pattern, normalized, flags=re.IGNORECASE)
        if matched:
            return f"Winner of {source_round} Match {matched.group(1)}"
    return normalized


def _team_name(team: Any) -> str | None:
    if team is None:
        return None
    return team.shortName or team.name


def _candidate_sort_key(match: ScoreboardMatch) -> tuple[int, str, str]:
    placeholder_count = sum(
        1
        for name in (_team_name(match.homeTeam), _team_name(match.awayTeam))
        if _is_placeholder_team(name)
    )
    return placeholder_count, match.kickoff or "", match.matchId


def _is_placeholder_team(value: str | None) -> bool:
    if not value:
        return True
    return bool(re.search(r"^(?:RD?32|R32|RD?16|R16|QF|SF|FINAL)\s*W\s*\d+$|^WINNER|^TBD$", value.strip(), re.IGNORECASE))


def _match_number(match: ScoreboardMatch) -> int | None:
    for value in (match.name, match.shortName, match.statusDescription):
        if not value:
            continue
        explicit = re.search(r"(?:MATCH|GAME)\s*#?\s*(\d{2,3})\b|#(\d{2,3})\b", value, re.IGNORECASE)
        if explicit:
            return int(next(group for group in explicit.groups() if group is not None))
        tournament_number = re.search(r"\b(7[3-9]|8\d|9\d|10[0-4])\b", value)
        if tournament_number:
            return int(tournament_number.group(1))
    return None


def _winner(match: ScoreboardMatch) -> str | None:
    home_score = match.homeTeam.score if match.homeTeam else None
    away_score = match.awayTeam.score if match.awayTeam else None
    if match.state != "post" or home_score is None or away_score is None or home_score == away_score:
        return None
    return match.homeTeam.id if home_score > away_score and match.homeTeam else match.awayTeam.id if match.awayTeam else None


def _match_date(match: ScoreboardMatch) -> date | None:
    return _parse_date(match.kickoff)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _stage_for_date(value: date) -> str:
    if value <= date(2026, 6, 27):
        return "Group Stage"
    if value <= date(2026, 7, 3):
        return "Round of 32"
    if value <= date(2026, 7, 7):
        return "Round of 16"
    if value <= date(2026, 7, 11):
        return "Quarterfinals"
    if value <= date(2026, 7, 15):
        return "Semifinals"
    if value <= WORLD_CUP_FINAL:
        return "Final Week"
    return "Completed"
