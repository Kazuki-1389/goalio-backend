from app.schemas.football import PlayerResult, TeamResult


TEAMS = [
    TeamResult(id="arg", name="Argentina", shortName="ARG", imageUrl="https://flagcdn.com/w320/ar.png"),
    TeamResult(id="bra", name="Brazil", shortName="BRA", imageUrl="https://flagcdn.com/w320/br.png"),
    TeamResult(id="eng", name="England", shortName="ENG", imageUrl="https://flagcdn.com/w320/gb-eng.png"),
    TeamResult(id="fra", name="France", shortName="FRA", imageUrl="https://flagcdn.com/w320/fr.png"),
    TeamResult(id="por", name="Portugal", shortName="POR", imageUrl="https://flagcdn.com/w320/pt.png"),
    TeamResult(id="esp", name="Spain", shortName="ESP", imageUrl="https://flagcdn.com/w320/es.png"),
]

PLAYERS = [
    PlayerResult(id="messi", name="Lionel Messi", team="Argentina", imageUrl="https://ui-avatars.com/api/?name=Lionel+Messi&size=512&background=75b9e7&color=ffffff"),
    PlayerResult(id="mbappe", name="Kylian Mbappe", team="France", imageUrl="https://ui-avatars.com/api/?name=Kylian+Mbappe&size=512&background=3159a7&color=ffffff"),
    PlayerResult(id="neymar", name="Neymar", team="Brazil", imageUrl="https://ui-avatars.com/api/?name=Neymar&size=512&background=f7d34a&color=101010"),
    PlayerResult(id="ronaldo", name="Cristiano Ronaldo", team="Portugal", imageUrl="https://ui-avatars.com/api/?name=Cristiano+Ronaldo&size=512&background=2b9a62&color=ffffff"),
    PlayerResult(id="bellingham", name="Jude Bellingham", team="England", imageUrl="https://ui-avatars.com/api/?name=Jude+Bellingham&size=512&background=ececec&color=101010"),
]


def search_teams(query: str) -> list[TeamResult]:
    needle = query.strip().casefold()
    return [team for team in TEAMS if not needle or needle in team.name.casefold()][:20]


def search_players(query: str) -> list[PlayerResult]:
    needle = query.strip().casefold()
    return [player for player in PLAYERS if not needle or needle in player.name.casefold() or needle in player.team.casefold()][:20]
