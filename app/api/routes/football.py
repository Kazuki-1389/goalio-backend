from fastapi import APIRouter, Depends, Query

from app.api.dependencies import CurrentUser, get_current_user
from app.schemas.football import PlayerResult, TeamResult
from app.services.football import search_players, search_teams


router = APIRouter(prefix="/football", tags=["football"])


@router.get("/teams/search", response_model=list[TeamResult])
def teams_search(
    q: str = Query(default="", max_length=80),
    _: CurrentUser = Depends(get_current_user),
) -> list[TeamResult]:
    return search_teams(q)


@router.get("/players/search", response_model=list[PlayerResult])
def players_search(
    q: str = Query(default="", max_length=80),
    _: CurrentUser = Depends(get_current_user),
) -> list[PlayerResult]:
    return search_players(q)
