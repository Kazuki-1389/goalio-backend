from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth

from app.core.config import get_settings
from app.core.firebase import get_firestore_client, initialize_firebase
from app.repositories.profiles import FirestoreProfileRepository, ProfileRepository


bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    uid: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> CurrentUser:
    settings = get_settings()
    if settings.allow_dev_auth and credentials and credentials.credentials.startswith("dev:"):
        return CurrentUser(credentials.credentials.removeprefix("dev:"))
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Firebase ID token")
    try:
        initialize_firebase()
        decoded = auth.verify_id_token(credentials.credentials, check_revoked=True)
        return CurrentUser(decoded["uid"])
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired Firebase ID token") from exc


@lru_cache
def get_profile_repository() -> ProfileRepository:
    return FirestoreProfileRepository(get_firestore_client())
