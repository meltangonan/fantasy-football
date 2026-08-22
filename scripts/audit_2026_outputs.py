#!/usr/bin/env python3
"""Fail loudly when the generated 2026 forecast violates core data contracts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "2026"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    model = json.loads((OUTPUT / "independent_forecast.json").read_text())
    board = json.loads((OUTPUT / "draft_board_data.json").read_text())
    players = board["players_by_model"]

    require(model["method"]["sleeper_used_as_feature"] is False, "Sleeper leaked into independent features")
    require(len(players) >= 200, "Draft pool is unexpectedly small")
    require(len({p["player_id"] for p in players}) == len(players), "Duplicate player IDs")
    require({p["position"] for p in players} >= {"QB", "RB", "WR", "TE"}, "Missing skill position")
    require(sorted(p["model_rank"] for p in players) == list(range(1, len(players) + 1)), "Decision ranks are not unique and continuous")
    require(sorted(p["independent_rank"] for p in players) == list(range(1, len(players) + 1)), "Independent ranks are not unique and continuous")
    require(all(p["projected_games"] > 0 for p in players), "Non-positive games forecast")
    require(all(p["team_pass_rank"] in range(1, 33) for p in players), "Invalid team pass rank")
    require(all(p["team_rush_rank"] in range(1, 33) for p in players), "Invalid team rush rank")

    selected = {"QB": "team_model_ppg", "RB": "player_only_ppg", "WR": "team_model_ppg", "TE": "team_model_ppg"}
    results = {(r["position"], r["model"]): r for r in model["backtest_overall"]}
    for position, model_name in selected.items():
        require(results[(position, model_name)]["players"] > 0, f"No {position} backtest rows")
        require(results[(position, model_name)]["mae"] <= results[(position, "prior_year_ppg")]["mae"] + 0.001, f"{position} model misses baseline")

    print(f"OK: {len(players)} players, continuous ranks, valid team context, and four position backtests")


if __name__ == "__main__":
    main()
