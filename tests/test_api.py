from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dependencies import CurrentUser, get_current_user, get_profile_repository
from app.main import app
from app.schemas.profile import ProfileUpsert, UserProfile


class MemoryProfiles:
    def __init__(self):
        self.profiles: dict[str, UserProfile] = {}

    def get(self, uid: str) -> UserProfile | None:
        return self.profiles.get(uid)

    def upsert(self, uid: str, profile: ProfileUpsert) -> UserProfile:
        now = datetime.now(UTC)
        saved = UserProfile(
            userId=uid,
            **profile.model_dump(),
            createdAt=self.profiles.get(uid, None).createdAt if uid in self.profiles else now,
            updatedAt=now,
            profileCompleted=True,
        )
        self.profiles[uid] = saved
        return saved


repository = MemoryProfiles()
app.dependency_overrides[get_current_user] = lambda: CurrentUser("test-user")
app.dependency_overrides[get_profile_repository] = lambda: repository
client = TestClient(app)


def test_profile_round_trip_and_personalized_home():
    payload = {
        "name": "Aegies",
        "username": "aegies",
        "favoriteTeams": ["Brazil", "Argentina"],
        "favoritePlayers": ["Lionel Messi", "Neymar"],
        "onboardingCompleted": True,
    }
    created = client.post("/api/v1/users/profile", json=payload)
    assert created.status_code == 200
    assert created.json()["userId"] == "test-user"
    assert created.json()["profileCompleted"] is True

    loaded = client.get("/api/v1/users/profile")
    assert loaded.status_code == 200
    assert loaded.json()["favoriteTeams"] == ["Brazil", "Argentina"]

    home = client.get("/api/v1/home")
    assert home.status_code == 200
    assert home.json()["greeting"] == "Welcome back, Aegies"


def test_search_teams_and_players():
    teams = client.get("/api/v1/football/teams/search?q=brazil")
    assert teams.status_code == 200
    assert [item["name"] for item in teams.json()] == ["Brazil"]

    players = client.get("/api/v1/football/players/search?q=messi")
    assert players.status_code == 200
    assert [item["name"] for item in players.json()] == ["Lionel Messi"]


def test_profile_validation():
    response = client.post(
        "/api/v1/users/profile",
        json={"name": "A", "username": "Bad username"},
    )
    assert response.status_code == 422
