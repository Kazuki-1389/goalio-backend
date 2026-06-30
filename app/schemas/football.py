from pydantic import BaseModel, Field


class TeamResult(BaseModel):
    id: str
    name: str
    shortName: str
    competitionIds: list[int] = Field(default_factory=list)
    imageUrl: str | None = None


class PlayerResult(BaseModel):
    id: str
    name: str
    team: str
    competitionIds: list[int] = Field(default_factory=list)
    imageUrl: str | None = None


class TeamPage(BaseModel):
    items: list[TeamResult]
    nextCursor: str | None = None


class PlayerPage(BaseModel):
    items: list[PlayerResult]
    nextCursor: str | None = None
