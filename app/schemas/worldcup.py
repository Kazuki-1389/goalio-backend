from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.matches import ScoreboardMatch, StandingTeam


class WorldCupTournament(BaseModel):
    id: str
    name: str
    stage: str
    hostCities: int
    daysToFinal: int | None = None
    lastSyncedAt: str | None = None


class WorldCupGroup(BaseModel):
    code: str
    teams: list[StandingTeam] = Field(default_factory=list)


BracketRoundCode = Literal["R32", "R16", "QF", "SF", "FINAL"]


class WorldCupNextMatchSlot(BaseModel):
    round: BracketRoundCode
    slotIndex: int = Field(ge=0)
    teamPosition: Literal["home", "away"]


class WorldCupBracketMatch(BaseModel):
    eventId: str
    round: BracketRoundCode
    slotIndex: int = Field(ge=0)
    status: str | None = None
    homeTeam: str | None = None
    awayTeam: str | None = None
    homeLogo: str | None = None
    awayLogo: str | None = None
    homeScore: int | None = None
    awayScore: int | None = None
    winnerTeamId: str | None = None
    kickoff: str | None = None
    nextMatchSlot: WorldCupNextMatchSlot | None = None


class WorldCupBracket(BaseModel):
    tournament: str
    bracketType: Literal["32_TEAM_KNOCKOUT"] = "32_TEAM_KNOCKOUT"
    rounds: dict[str, list[WorldCupBracketMatch]] = Field(default_factory=dict)


class WorldCupLibraryItem(BaseModel):
    id: str
    title: str
    category: str
    body: str
    readMinutes: int


class WorldCupFact(BaseModel):
    title: str
    body: str


class WorldCupBootstrap(BaseModel):
    tournament: WorldCupTournament
    liveMatches: list[ScoreboardMatch] = Field(default_factory=list)
    todayMatches: list[ScoreboardMatch] = Field(default_factory=list)
    upcomingMatches: list[ScoreboardMatch] = Field(default_factory=list)
    recentResults: list[ScoreboardMatch] = Field(default_factory=list)
    groups: list[WorldCupGroup] = Field(default_factory=list)
    bracket: WorldCupBracket
    library: list[WorldCupLibraryItem] = Field(default_factory=list)
    randomFact: WorldCupFact
