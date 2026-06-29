from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import CurrentUser, get_current_user, get_profile_repository
from app.repositories.profiles import ProfileRepository
from app.schemas.profile import PersonalizedHome, ProfileUpsert, UserProfile


router = APIRouter(tags=["users"])


@router.post("/users/profile", response_model=UserProfile)
def save_profile(
    payload: ProfileUpsert,
    user: CurrentUser = Depends(get_current_user),
    repository: ProfileRepository = Depends(get_profile_repository),
) -> UserProfile:
    return repository.upsert(user.uid, payload)


@router.get("/users/profile", response_model=UserProfile)
def get_profile(
    user: CurrentUser = Depends(get_current_user),
    repository: ProfileRepository = Depends(get_profile_repository),
) -> UserProfile:
    profile = repository.get(user.uid)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return profile


@router.get("/home", response_model=PersonalizedHome)
def get_home(
    user: CurrentUser = Depends(get_current_user),
    repository: ProfileRepository = Depends(get_profile_repository),
) -> PersonalizedHome:
    profile = repository.get(user.uid)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first")
    first_name = profile.name.split()[0]
    return PersonalizedHome(profile=profile, greeting=f"Welcome back, {first_name}")
