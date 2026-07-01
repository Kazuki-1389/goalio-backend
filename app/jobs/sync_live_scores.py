from __future__ import annotations

import argparse
from datetime import date, timedelta
import time

from app.core.firebase import get_firestore_client
from app.services.match_detail import EspnMatchDetailClient, FirestoreScoreboardStore


DEFAULT_LEAGUES = (
    "fifa.world", "eng.1", "esp.1", "ita.1", "ger.1", "fra.1",
    "uefa.champions", "uefa.europa",
)
REFRESH_SECONDS = 120


def sync_once(client: EspnMatchDetailClient, store: FirestoreScoreboardStore, leagues: tuple[str, ...]) -> tuple[int, int]:
    today = date.today()
    ranges = (
        (today.isoformat(), today.isoformat()),
        ((today - timedelta(days=30)).isoformat(), (today + timedelta(days=120)).isoformat()),
    )
    written = failures = 0
    for league in leagues:
        for from_date, to_date in ranges:
            try:
                client.cached_schedule(league, store, from_date=from_date, to_date=to_date, force=True)
                written += 1
            except Exception as exc:
                failures += 1
                print(f"LIVE_SCORE_SYNC_FAILED league={league} range={from_date}/{to_date} reason={str(exc)[:160]}")
    print(f"live_score_sync written={written} failures={failures}")
    return written, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh shared Firestore scoreboards every two minutes.")
    parser.add_argument("--league", action="append", dest="leagues")
    parser.add_argument("--watch", action="store_true", help="Run continuously at a 120-second cadence.")
    args = parser.parse_args()
    client = EspnMatchDetailClient()
    store = FirestoreScoreboardStore(get_firestore_client())
    leagues = tuple(args.leagues or DEFAULT_LEAGUES)
    while True:
        started = time.monotonic()
        sync_once(client, store, leagues)
        if not args.watch:
            break
        time.sleep(max(1, REFRESH_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
