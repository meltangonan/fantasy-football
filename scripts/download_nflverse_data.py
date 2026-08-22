#!/usr/bin/env python3
"""Download the public NFLverse inputs used by the independent forecast."""

from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "data" / "raw" / "nflverse"
SEASONS = range(2015, 2026)
BASE = "https://github.com/nflverse/nflverse-data/releases/download"


def download(url: str, destination: Path, force: bool) -> None:
    if destination.exists() and not force:
        print(f"keep {destination.relative_to(ROOT)}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "fantasy-football-model/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    temporary.replace(destination)
    print(f"saved {destination.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace files that already exist")
    args = parser.parse_args()

    jobs = []
    for season in SEASONS:
        jobs.extend(
            [
                (f"{BASE}/stats_player/stats_player_reg_{season}.csv", DESTINATION / f"stats_player_reg_{season}.csv"),
                (f"{BASE}/stats_team/stats_team_reg_{season}.csv", DESTINATION / f"stats_team_reg_{season}.csv"),
            ]
        )
    jobs.extend(
        [
            (f"{BASE}/players/players.csv", DESTINATION / "players.csv"),
            (f"{BASE}/draft_picks/draft_picks.csv", DESTINATION / "draft_picks.csv"),
        ]
    )
    for url, destination in jobs:
        download(url, destination, args.force)


if __name__ == "__main__":
    main()
