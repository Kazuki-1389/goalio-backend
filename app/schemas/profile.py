from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileUpsert(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    username: str = Field(min_length=3, max_length=20, pattern=r"^[a-z0-9_]+$")
    favoriteTeams: list[str] = Field(default_factory=list, max_length=20)
    favoritePlayers: list[str] = Field(default_factory=list, max_length=20)
    onboardingCompleted: bool = True

    @field_validator("name", "username")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("favoriteTeams", "favoritePlayers")
    @classmethod
    def clean_favorites(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in cleaned:
                cleaned.append(item[:80])
        return cleaned


class UserProfile(ProfileUpsert):
    userId: str
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    profileCompleted: bool = True

    model_config = ConfigDict(from_attributes=True)


class PersonalizedHome(BaseModel):
    profile: UserProfile
    greeting: str
