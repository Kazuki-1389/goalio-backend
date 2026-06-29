from pydantic import BaseModel


class TeamResult(BaseModel):
    id: str
    name: str
    shortName: str
    imageUrl: str | None = None


class PlayerResult(BaseModel):
    id: str
    name: str
    team: str
    imageUrl: str | None = None
