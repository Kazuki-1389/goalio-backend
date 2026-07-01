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
    "R32": [73, 75, 74, 77, 83, 84, 81, 82, 76, 78, 79, 80, 86, 88, 85, 87],
    "R16": [89, 90, 93, 94, 91, 92, 95, 96],
    "QF": [97, 98, 99, 100],
    "SF": [101, 102],
    "FINAL": [104],
}
EVENT_SLOT_TOPOLOGY = {
    "R32": {
        "760486": 0, "760488": 1, "760489": 2, "760492": 3,
        "760496": 4, "760497": 5, "760494": 6, "760493": 7,
        "760487": 8, "760490": 9, "760491": 10, "760495": 11,
        "760500": 12, "760499": 13, "760498": 14, "760501": 15,
    },
    "R16": {
        "760502": 0, "760503": 1, "760506": 2, "760507": 3,
        "760504": 4, "760505": 5, "760508": 6, "760509": 7,
    },
    "QF": {"760510": 0, "760512": 1, "760511": 2, "760513": 3},
    "SF": {"760514": 0, "760515": 1},
    "FINAL": {"760517": 0},
}
ROUND_CODES = ("R32", "R16", "QF", "SF", "FINAL")
ROUND_SLOT_COUNTS = {"R32": 16, "R16": 8, "QF": 4, "SF": 2, "FINAL": 1}
NEXT_SLOT_TOPOLOGY = {
    "R32": [("R16", index // 2, "home" if index % 2 == 0 else "away") for index in range(16)],
    "R16": [
        ("QF", 0, "away"),
        ("QF", 0, "home"),
        ("QF", 1, "home"),
        ("QF", 1, "away"),
        ("QF", 2, "home"),
        ("QF", 2, "away"),
        ("QF", 3, "home"),
        ("QF", 3, "away"),
    ],
    "QF": [("SF", index // 2, "home" if index % 2 == 0 else "away") for index in range(4)],
    "SF": [("FINAL", 0, "home" if index == 0 else "away") for index in range(2)],
}


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
            slot_index = EVENT_SLOT_TOPOLOGY.get(round_code, {}).get(match.matchId)
            if slot_index is None:
                slot_index = number_slots.get(match_number) if match_number is not None else _placeholder_slot_hint(match, round_code)
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

    _validate_normalized_bracket(normalized)
    return WorldCupBracket(
        tournament="FIFA World Cup",
        bracketType="32_TEAM_KNOCKOUT",
        rounds=normalized,
    )


def _validate_normalized_bracket(rounds: dict[str, list[WorldCupBracketMatch]]) -> None:
    for round_code, expected_count in ROUND_SLOT_COUNTS.items():
        matches = rounds.get(round_code, [])
        if len(matches) != expected_count:
            raise ValueError(f"{round_code} must contain {expected_count} bracket slots")
        if [match.slotIndex for match in matches] != list(range(expected_count)):
            raise ValueError(f"{round_code} slot indexes must be contiguous")

    incoming: dict[tuple[str, int], list[WorldCupNextMatchSlot]] = {}
    for round_code in ROUND_CODES[:-1]:
        for match in rounds[round_code]:
            target = match.nextMatchSlot
            if target is None:
                raise ValueError(f"{round_code} slot {match.slotIndex} has no next match")
            if target.slotIndex >= len(rounds[target.round]):
                raise ValueError(f"{round_code} slot {match.slotIndex} points outside {target.round}")
            incoming.setdefault((target.round, target.slotIndex), []).append(target)

    for target_round in ROUND_CODES[1:]:
        for target in rounds[target_round]:
            sources = incoming.get((target_round, target.slotIndex), [])
            if len(sources) != 2 or {source.teamPosition for source in sources} != {"home", "away"}:
                raise ValueError(f"{target_round} slot {target.slotIndex} must receive home and away sources")


def _normalized_match(match: ScoreboardMatch, round_code: str, slot_index: int) -> WorldCupBracketMatch:
    home_team = _normalized_team_name(_team_name(match.homeTeam))
    away_team = _normalized_team_name(_team_name(match.awayTeam))
    if _is_placeholder_team(home_team):
        home_team = _incoming_winner_label(round_code, slot_index, "home") or home_team
    if _is_placeholder_team(away_team):
        away_team = _incoming_winner_label(round_code, slot_index, "away") or away_team
    return WorldCupBracketMatch(
        eventId=match.matchId,
        round=round_code,
        slotIndex=slot_index,
        status=match.status or match.statusDescription,
        homeTeam=home_team,
        awayTeam=away_team,
        homeLogo=match.homeTeam.logo if match.homeTeam else None,
        awayLogo=match.awayTeam.logo if match.awayTeam else None,
        homeScore=match.homeTeam.score if match.homeTeam else None,
        awayScore=match.awayTeam.score if match.awayTeam else None,
        winnerTeamId=_winner(match),
        kickoff=match.kickoff,
        nextMatchSlot=_next_match_slot(round_code, slot_index),
    )


def _placeholder_match(round_code: str, slot_index: int) -> WorldCupBracketMatch:
    incoming = _incoming_slots(round_code, slot_index)
    if not incoming:
        home_team = away_team = "TBD"
    else:
        by_position = {position: (source_round, source_slot) for source_round, source_slot, position in incoming}
        home_source = by_position.get("home")
        away_source = by_position.get("away")
        home_team = _winner_label(home_source)
        away_team = _winner_label(away_source)
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
    topology = NEXT_SLOT_TOPOLOGY.get(round_code)
    if topology is None or slot_index not in range(len(topology)):
        return None
    next_round, next_slot, team_position = topology[slot_index]
    return WorldCupNextMatchSlot(
        round=next_round,
        slotIndex=next_slot,
        teamPosition=team_position,
    )


def _incoming_slots(target_round: str, target_slot: int) -> list[tuple[str, int, str]]:
    incoming: list[tuple[str, int, str]] = []
    for source_round, destinations in NEXT_SLOT_TOPOLOGY.items():
        for source_slot, (round_code, slot_index, position) in enumerate(destinations):
            if round_code == target_round and slot_index == target_slot:
                incoming.append((source_round, source_slot, position))
    return incoming


def _winner_label(source: tuple[str, int] | None) -> str:
    if source is None:
        return "TBD"
    source_round, source_slot = source
    return f"Winner of {source_round} Match {source_slot + 1}"


def _incoming_winner_label(target_round: str, target_slot: int, position: str) -> str | None:
    source = next(
        (
            (source_round, source_slot)
            for source_round, source_slot, team_position in _incoming_slots(target_round, target_slot)
            if team_position == position
        ),
        None,
    )
    return _winner_label(source) if source is not None else None


def _round_code(match: ScoreboardMatch, match_number: int | None) -> str | None:
    for round_code, event_slots in EVENT_SLOT_TOPOLOGY.items():
        if match.matchId in event_slots:
            return round_code

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
    if "semifinal" in joined and "loser" in joined:
        return None
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
        (r"(?:RD?32|R32)\s*W|WINNER\s+OF\s+R32|ROUND\s+OF\s+32\s+\d+\s+WINNER", "R16"),
        (r"(?:RD?16|R16)\s*W|WINNER\s+OF\s+R16|ROUND\s+OF\s+16\s+\d+\s+WINNER", "QF"),
        (r"QF\s*W|WINNER\s+OF\s+QF|QUARTERFINALS?\s+\d+\s+WINNER", "SF"),
        (r"SF\s*W|WINNER\s+OF\s+SF|SEMIFINALS?\s+\d+\s+WINNER", "FINAL"),
    )
    return next((round_code for pattern, round_code in checks if re.search(pattern, joined)), None)


def _placeholder_slot_hint(match: ScoreboardMatch, target_round: str) -> int | None:
    references: list[tuple[str, int]] = []
    patterns = {
        "R32": r"(?:RD?32|R32)\s*W\s*(\d+)|WINNER\s+OF\s+R32\s+MATCH\s+(\d+)|ROUND\s+OF\s+32\s+(\d+)\s+WINNER",
        "R16": r"(?:RD?16|R16)\s*W\s*(\d+)|WINNER\s+OF\s+R16\s+MATCH\s+(\d+)|ROUND\s+OF\s+16\s+(\d+)\s+WINNER",
        "QF": r"QF\s*W\s*(\d+)|WINNER\s+OF\s+QF\s+MATCH\s+(\d+)|QUARTERFINALS?\s+(\d+)\s+WINNER",
        "SF": r"SF\s*W\s*(\d+)|WINNER\s+OF\s+SF\s+MATCH\s+(\d+)|SEMIFINALS?\s+(\d+)\s+WINNER",
    }
    for team_name in (_team_name(match.homeTeam), _team_name(match.awayTeam)):
        if not team_name:
            continue
        for source_round, pattern in patterns.items():
            found = re.search(pattern, team_name, re.IGNORECASE)
            if found:
                source_number = int(next(group for group in found.groups() if group is not None))
                references.append((source_round, source_number - 1))

    targets = {
        topology[source_slot][1]
        for source_round, source_slot in references
        if (topology := NEXT_SLOT_TOPOLOGY.get(source_round)) is not None
        and source_slot in range(len(topology))
        and topology[source_slot][0] == target_round
    }
    return next(iter(targets)) if len(targets) == 1 else None


def _normalized_team_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    replacements = (
        (r"(?:RD?32\s*W\s*|ROUND\s+OF\s+32\s+)(\d+)(?:\s+WINNER)?", "R32"),
        (r"(?:RD?16\s*W\s*|ROUND\s+OF\s+16\s+)(\d+)(?:\s+WINNER)?", "R16"),
        (r"(?:QF\s*W\s*|QUARTERFINALS?\s+)(\d+)(?:\s+WINNER)?", "QF"),
        (r"(?:SF\s*W\s*|SEMIFINALS?\s+)(\d+)(?:\s+WINNER)?", "SF"),
    )
    for pattern, source_round in replacements:
        matched = re.fullmatch(pattern, normalized, flags=re.IGNORECASE)
        if matched:
            return f"Winner of {source_round} Match {matched.group(1)}"
    return normalized


def _team_name(team: Any) -> str | None:
    if team is None:
        return None
    return team.shortName or team.name


def _candidate_sort_key(match: ScoreboardMatch) -> tuple[int, str]:
    placeholder_count = sum(
        1
        for name in (_team_name(match.homeTeam), _team_name(match.awayTeam))
        if _is_placeholder_team(name)
    )
    return placeholder_count, match.matchId


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
