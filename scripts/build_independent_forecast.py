#!/usr/bin/env python3
"""Build a team-aware, independent 2026 PPR forecast and backtest it.

The model never uses Sleeper projections or ADP as predictive features. It
learns how one NFL season predicts the next from NFLverse regular-season data.
Team pass/run environment is forecast from the destination team's prior three
seasons and supplied to each position-specific player model.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from build_2026_draft_data import (
    parse_fantasypros_history,
    resolve_players,
)


ROOT = Path(__file__).resolve().parents[1]
NFLVERSE_DIR = ROOT / "data" / "raw" / "nflverse"
RAW_2026_DIR = ROOT / "data" / "raw" / "2026"
OUTPUT_DIR = ROOT / "outputs" / "2026"
POSITIONS = ("QB", "RB", "WR", "TE")
SEASONS = tuple(range(2015, 2026))
TEAM_SOURCE = "https://github.com/nflverse/nflverse-data/releases/tag/stats_team"
PLAYER_SOURCE = "https://github.com/nflverse/nflverse-data/releases/tag/stats_player"
DRAFT_SOURCE = "https://github.com/nflverse/nflverse-data/releases/tag/draft_picks"
PLAYERS_SOURCE = "https://github.com/nflverse/nflverse-data/releases/tag/players"

TEAM_FEATURES = [
    "next_team_plays_pg",
    "next_team_pass_attempts_pg",
    "next_team_carries_pg",
    "next_team_pass_rate",
    "next_team_pass_yards_pg",
    "next_team_rush_yards_pg",
    "next_team_pass_tds_pg",
    "next_team_rush_tds_pg",
    "next_team_pass_epa_per_attempt",
    "next_team_rush_epa_per_carry",
]

PLAYER_FEATURES = [
    "age_at_target",
    "age_squared",
    "years_exp_at_target",
    "log_draft_pick",
    "undrafted",
    "gap_years",
    "team_change",
    "games",
    "fantasy_ppg",
    "pass_attempts_pg",
    "pass_yards_pg",
    "pass_tds_pg",
    "interceptions_pg",
    "carries_pg",
    "rush_yards_pg",
    "rush_tds_pg",
    "targets_pg",
    "receptions_pg",
    "rec_yards_pg",
    "rec_tds_pg",
    "target_share",
    "carry_share",
    "catch_rate",
    "pass_ypa",
    "rush_ypc",
    "rec_ypt",
    "pass_td_rate",
    "interception_rate",
    "rush_td_rate",
    "rec_td_rate",
    "passing_epa_pg",
    "rushing_epa_pg",
    "receiving_epa_pg",
    "prev_games",
    "prev_fantasy_ppg",
    "prev_targets_pg",
    "prev_carries_pg",
    "prev_target_share",
    "prev_carry_share",
]

COMPONENT_TARGETS = {
    "QB": [
        "pass_attempts_pg",
        "completions_pg",
        "pass_yards_pg",
        "pass_tds_pg",
        "interceptions_pg",
        "carries_pg",
        "rush_yards_pg",
        "rush_tds_pg",
    ],
    "RB": [
        "targets_pg",
        "receptions_pg",
        "rec_yards_pg",
        "rec_tds_pg",
        "carries_pg",
        "rush_yards_pg",
        "rush_tds_pg",
    ],
    "WR": [
        "targets_pg",
        "receptions_pg",
        "rec_yards_pg",
        "rec_tds_pg",
        "carries_pg",
        "rush_yards_pg",
        "rush_tds_pg",
    ],
    "TE": [
        "targets_pg",
        "receptions_pg",
        "rec_yards_pg",
        "rec_tds_pg",
        "carries_pg",
        "rush_yards_pg",
        "rush_tds_pg",
    ],
}


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", text.lower())
    return re.sub(r"[^a-z0-9]", "", text)


def safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.div(denominator.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def age_on_season_start(birth_date: Any, season: int) -> float:
    try:
        born = date.fromisoformat(str(birth_date)[:10])
        kickoff = date(season, 9, 1)
        return (kickoff - born).days / 365.2425
    except (TypeError, ValueError):
        return np.nan


def load_history() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    player_frames = [pd.read_csv(NFLVERSE_DIR / f"stats_player_reg_{season}.csv", low_memory=False) for season in SEASONS]
    team_frames = [pd.read_csv(NFLVERSE_DIR / f"stats_team_reg_{season}.csv", low_memory=False) for season in SEASONS]
    players = pd.read_csv(NFLVERSE_DIR / "players.csv", low_memory=False)
    draft = pd.read_csv(NFLVERSE_DIR / "draft_picks.csv", low_memory=False)
    player = pd.concat(player_frames, ignore_index=True)
    team = pd.concat(team_frames, ignore_index=True)
    return player, team, players, draft


def prepare_team_history(team: pd.DataFrame) -> pd.DataFrame:
    team = team.copy()
    games = team["games"].replace(0, np.nan)
    team["plays_pg"] = (team["attempts"] + team["sacks_suffered"] + team["carries"]) / games
    team["pass_attempts_pg"] = team["attempts"] / games
    team["carries_pg"] = team["carries"] / games
    team["pass_rate"] = safe_div(team["attempts"] + team["sacks_suffered"], team["attempts"] + team["sacks_suffered"] + team["carries"])
    team["pass_yards_pg"] = team["passing_yards"] / games
    team["rush_yards_pg"] = team["rushing_yards"] / games
    team["pass_tds_pg"] = team["passing_tds"] / games
    team["rush_tds_pg"] = team["rushing_tds"] / games
    team["pass_epa_per_attempt"] = safe_div(team["passing_epa"], team["attempts"])
    team["rush_epa_per_carry"] = safe_div(team["rushing_epa"], team["carries"])
    keep = ["season", "team", "games"] + [name.replace("next_team_", "") for name in TEAM_FEATURES]
    return team[keep].sort_values(["team", "season"]).reset_index(drop=True)


def team_forecast(team_history: pd.DataFrame, team: str, origin_season: int) -> dict[str, float]:
    """Forecast a destination team's next season from information known by origin_season."""
    metrics = [name.replace("next_team_", "") for name in TEAM_FEATURES]
    rows = team_history[(team_history["team"] == team) & (team_history["season"] <= origin_season)].sort_values("season", ascending=False).head(3)
    league = team_history[team_history["season"] == origin_season]
    weights = np.array([0.55, 0.30, 0.15])[: len(rows)]
    if len(weights):
        weights = weights / weights.sum()
    result: dict[str, float] = {}
    for metric in metrics:
        league_mean = float(league[metric].mean()) if len(league) else float(team_history[metric].mean())
        if len(rows):
            raw = float(np.average(rows[metric].fillna(league_mean), weights=weights))
        else:
            raw = league_mean
        # Team volume is persistent but coaching/QB changes make exact ranks noisy.
        result[f"next_team_{metric}"] = 0.80 * raw + 0.20 * league_mean
    return result


def prepare_player_history(player: pd.DataFrame, team_history: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    p = player[player["position"].isin(POSITIONS)].copy()
    p = p.sort_values(["player_id", "season"]).drop_duplicates(["player_id", "season"], keep="last")
    profile = players[["gsis_id", "birth_date", "rookie_season", "draft_pick", "draft_round"]].drop_duplicates("gsis_id")
    p = p.merge(profile, left_on="player_id", right_on="gsis_id", how="left")
    games = p["games"].replace(0, np.nan)
    p["fantasy_ppg"] = p["fantasy_points_ppr"] / games
    p["completions_pg"] = p["completions"] / games
    p["pass_attempts_pg"] = p["attempts"] / games
    p["pass_yards_pg"] = p["passing_yards"] / games
    p["pass_tds_pg"] = p["passing_tds"] / games
    p["interceptions_pg"] = p["passing_interceptions"] / games
    p["carries_pg"] = p["carries"] / games
    p["rush_yards_pg"] = p["rushing_yards"] / games
    p["rush_tds_pg"] = p["rushing_tds"] / games
    p["targets_pg"] = p["targets"] / games
    p["receptions_pg"] = p["receptions"] / games
    p["rec_yards_pg"] = p["receiving_yards"] / games
    p["rec_tds_pg"] = p["receiving_tds"] / games
    p["catch_rate"] = safe_div(p["receptions"], p["targets"])
    p["pass_ypa"] = safe_div(p["passing_yards"], p["attempts"])
    p["rush_ypc"] = safe_div(p["rushing_yards"], p["carries"])
    p["rec_ypt"] = safe_div(p["receiving_yards"], p["targets"])
    p["pass_td_rate"] = safe_div(p["passing_tds"], p["attempts"])
    p["interception_rate"] = safe_div(p["passing_interceptions"], p["attempts"])
    p["rush_td_rate"] = safe_div(p["rushing_tds"], p["carries"])
    p["rec_td_rate"] = safe_div(p["receiving_tds"], p["targets"])
    p["passing_epa_pg"] = p["passing_epa"] / games
    p["rushing_epa_pg"] = p["rushing_epa"] / games
    p["receiving_epa_pg"] = p["receiving_epa"] / games
    team_carries = team_history[["season", "team", "carries_pg"]].rename(columns={"carries_pg": "team_carries_pg"})
    p = p.merge(team_carries, left_on=["season", "recent_team"], right_on=["season", "team"], how="left").drop(columns=["team"])
    p["carry_share"] = safe_div(p["carries_pg"], p["team_carries_pg"])
    p["target_share"] = p["target_share"].fillna(0.0)
    p["draft_pick"] = p["draft_pick"].fillna(300.0)
    p["log_draft_pick"] = np.log1p(p["draft_pick"].clip(lower=1))
    p["undrafted"] = (p["draft_pick"] >= 300).astype(float)
    for column in ["games", "fantasy_ppg", "targets_pg", "carries_pg", "target_share", "carry_share"]:
        p[f"prev_{column}"] = p.groupby("player_id")[column].shift(1)
    return p


def build_transition_rows(history: pd.DataFrame, team_history: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    indexed = {(str(row.player_id), int(row.season)): row for row in history.itertuples(index=False)}
    for origin in history.itertuples(index=False):
        target_season = int(origin.season) + 1
        if target_season > 2025 or int(origin.games) < 3:
            continue
        target = indexed.get((str(origin.player_id), target_season))
        target_team = str(target.recent_team) if target is not None else str(origin.recent_team)
        born = getattr(origin, "birth_date", None)
        age = age_on_season_start(born, target_season)
        rookie = getattr(origin, "rookie_season", np.nan)
        years_exp = target_season - int(rookie) if pd.notna(rookie) else np.nan
        record = {column: getattr(origin, column, np.nan) for column in PLAYER_FEATURES if hasattr(origin, column)}
        record.update(
            {
                "player_id": str(origin.player_id),
                "player": origin.player_display_name,
                "position": origin.position,
                "origin_season": int(origin.season),
                "target_season": target_season,
                "origin_team": origin.recent_team,
                "target_team": target_team,
                "age_at_target": age,
                "age_squared": age * age if pd.notna(age) else np.nan,
                "years_exp_at_target": years_exp,
                "gap_years": 1.0,
                "team_change": float(target_team != str(origin.recent_team)),
                "target_games": float(target.games) if target is not None else 0.0,
                "target_fantasy_points": float(target.fantasy_points_ppr) if target is not None else 0.0,
                "target_fantasy_ppg": float(target.fantasy_ppg) if target is not None else np.nan,
            }
        )
        if target is not None:
            for component in set(sum(COMPONENT_TARGETS.values(), [])):
                record[f"target_{component}"] = float(getattr(target, component, 0.0) or 0.0)
        record.update(team_forecast(team_history, target_team, int(origin.season)))
        rows.append(record)
    return pd.DataFrame(rows)


def model_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("ridge", RidgeCV(alphas=np.logspace(-2, 4, 13))),
        ]
    )


@dataclass
class PositionModels:
    ppg: Pipeline
    games: Pipeline
    components: dict[str, Pipeline]


def fit_position_models(
    rows: pd.DataFrame,
    position: str,
    features: list[str],
    ppg_features: list[str],
) -> PositionModels:
    subset = rows[rows["position"] == position].copy()
    active = subset[subset["target_games"] >= 4]
    ppg = model_pipeline().fit(active[ppg_features], active["target_fantasy_ppg"])
    games = model_pipeline().fit(subset[features], subset["target_games"])
    components = {
        component: model_pipeline().fit(active[features], active[f"target_{component}"])
        for component in COMPONENT_TARGETS[position]
    }
    return PositionModels(ppg=ppg, games=games, components=components)


def backtest(transitions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    prediction_rows: list[dict[str, Any]] = []
    team_features = PLAYER_FEATURES + TEAM_FEATURES
    player_only = PLAYER_FEATURES
    for test_year in range(2021, 2026):
        train = transitions[transitions["target_season"] < test_year]
        test = transitions[(transitions["target_season"] == test_year) & (transitions["target_games"] >= 4)]
        for position in POSITIONS:
            train_pos = train[(train["position"] == position) & (train["target_games"] >= 4)]
            test_pos = test[test["position"] == position]
            if len(train_pos) < 40 or test_pos.empty:
                continue
            aware = model_pipeline().fit(train_pos[team_features], train_pos["target_fantasy_ppg"])
            plain = model_pipeline().fit(train_pos[player_only], train_pos["target_fantasy_ppg"])
            aware_pred = np.clip(aware.predict(test_pos[team_features]), 0, None)
            plain_pred = np.clip(plain.predict(test_pos[player_only]), 0, None)
            for (_, row), aware_value, plain_value in zip(test_pos.iterrows(), aware_pred, plain_pred):
                prediction_rows.append(
                    {
                        "season": test_year,
                        "position": position,
                        "player": row["player"],
                        "actual_ppg": row["target_fantasy_ppg"],
                        "team_model_ppg": aware_value,
                        "player_only_ppg": plain_value,
                        "prior_year_ppg": row["fantasy_ppg"],
                    }
                )
    predictions = pd.DataFrame(prediction_rows)
    metrics: list[dict[str, Any]] = []
    for (position, season), group in predictions.groupby(["position", "season"]):
        for model_name in ["team_model_ppg", "player_only_ppg", "prior_year_ppg"]:
            valid = group[["actual_ppg", model_name]].dropna()
            corr = spearmanr(valid["actual_ppg"], valid[model_name]).statistic if len(valid) >= 3 else np.nan
            metrics.append(
                {
                    "position": position,
                    "season": int(season),
                    "model": model_name,
                    "players": len(valid),
                    "mae": float(np.mean(np.abs(valid["actual_ppg"] - valid[model_name]))),
                    "rank_correlation": float(corr),
                }
            )
    summary = pd.DataFrame(metrics)
    return predictions, summary


def rookie_training_rows(history: pd.DataFrame, draft: pd.DataFrame, team_history: pd.DataFrame) -> pd.DataFrame:
    drafted = draft[(draft["season"].between(2015, 2025)) & (draft["position"].isin(POSITIONS))][
        ["season", "round", "pick", "team", "gsis_id", "pfr_player_name", "position", "age"]
    ].copy()
    rookies = history[["player_id", "season", "games", "fantasy_points_ppr", "fantasy_ppg"]].copy()
    merged = drafted.merge(rookies, left_on=["gsis_id", "season"], right_on=["player_id", "season"], how="left")
    merged["games"] = merged["games"].fillna(0.0)
    merged["fantasy_points_ppr"] = merged["fantasy_points_ppr"].fillna(0.0)
    merged["fantasy_ppg"] = merged["fantasy_ppg"].fillna(0.0)
    merged["log_draft_pick"] = np.log1p(merged["pick"].clip(lower=1))
    merged["age"] = merged["age"].fillna(22.0)
    for index, row in merged.iterrows():
        env = team_forecast(team_history, str(row["team"]), int(row["season"]) - 1)
        for key, value in env.items():
            merged.at[index, key] = value
    return merged


def fit_rookie_models(rookies: pd.DataFrame) -> dict[str, dict[str, Pipeline]]:
    features = ["log_draft_pick", "age"] + TEAM_FEATURES
    result: dict[str, dict[str, Pipeline]] = {}
    for position in POSITIONS:
        subset = rookies[rookies["position"] == position]
        result[position] = {
            "points": model_pipeline().fit(subset[features], subset["fantasy_points_ppr"]),
            "games": model_pipeline().fit(subset[features], subset["games"]),
        }
    return result


def resolve_nflverse_profile(name: str, position: str, profiles: pd.DataFrame) -> pd.Series | None:
    matches = profiles[(profiles["normalized_name"] == normalize_name(name)) & (profiles["position"].fillna(profiles["position_group"]) == position)]
    if matches.empty:
        matches = profiles[profiles["normalized_name"] == normalize_name(name)]
    if matches.empty:
        return None
    return matches.sort_values(["last_season", "rookie_season"], ascending=False).iloc[0]


def current_feature_row(
    player: dict[str, Any],
    profile: pd.Series,
    history: pd.DataFrame,
    team_history: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series | None]:
    player_history = history[history["player_id"] == profile["gsis_id"]].sort_values("season")
    latest = player_history[player_history["season"] <= 2025].tail(1)
    if latest.empty:
        return pd.DataFrame(), None
    origin = latest.iloc[0]
    target_team = "LA" if player["team"] == "LAR" else player["team"]
    age = age_on_season_start(profile.get("birth_date"), 2026)
    rookie_season = profile.get("rookie_season")
    years_exp = 2026 - int(rookie_season) if pd.notna(rookie_season) else player.get("years_exp")
    record = {column: origin.get(column, np.nan) for column in PLAYER_FEATURES}
    record.update(
        {
            "age_at_target": age,
            "age_squared": age * age if pd.notna(age) else np.nan,
            "years_exp_at_target": years_exp,
            "gap_years": 2026 - int(origin["season"]),
            "team_change": float(target_team != origin["recent_team"]),
        }
    )
    record.update(team_forecast(team_history, target_team, 2025))
    return pd.DataFrame([record]), origin


def component_fantasy_ppg(position: str, values: dict[str, float]) -> float:
    if position == "QB":
        return (
            values.get("pass_yards_pg", 0) / 25
            + values.get("pass_tds_pg", 0) * 4
            - values.get("interceptions_pg", 0) * 2
            + values.get("rush_yards_pg", 0) / 10
            + values.get("rush_tds_pg", 0) * 6
        )
    return (
        values.get("receptions_pg", 0)
        + values.get("rec_yards_pg", 0) / 10
        + values.get("rec_tds_pg", 0) * 6
        + values.get("rush_yards_pg", 0) / 10
        + values.get("rush_tds_pg", 0) * 6
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    player_raw, team_raw, profiles, draft = load_history()
    team_history = prepare_team_history(team_raw)
    history = prepare_player_history(player_raw, team_history, profiles)
    transitions = build_transition_rows(history, team_history)

    backtest_predictions, backtest_summary = backtest(transitions)
    backtest_predictions.to_csv(OUTPUT_DIR / "backtest_predictions.csv", index=False)
    backtest_summary.to_csv(OUTPUT_DIR / "backtest_summary.csv", index=False)

    features = PLAYER_FEATURES + TEAM_FEATURES
    ppg_features_by_position = {
        position: (PLAYER_FEATURES if position == "RB" else features)
        for position in POSITIONS
    }
    models = {
        position: fit_position_models(transitions, position, features, ppg_features_by_position[position])
        for position in POSITIONS
    }
    rookie_rows = rookie_training_rows(history, draft, team_history)
    rookie_models = fit_rookie_models(rookie_rows)

    team_2026 = []
    for team in sorted(team_history[team_history["season"] == 2025]["team"].unique()):
        team_2026.append({"team": team, **team_forecast(team_history, team, 2025)})
    team_2026_df = pd.DataFrame(team_2026)
    team_2026_df["team_pass_rank"] = team_2026_df["next_team_pass_attempts_pg"].rank(method="min", ascending=False).astype(int)
    team_2026_df["team_rush_rank"] = team_2026_df["next_team_carries_pg"].rank(method="min", ascending=False).astype(int)
    team_environment = team_2026_df.set_index("team").to_dict(orient="index")

    live_raw = json.loads((RAW_2026_DIR / "sleeper_live_2026.json").read_text())
    metadata_raw = json.loads((RAW_2026_DIR / "sleeper_players.json").read_text())
    fantasypros_raw = json.loads((RAW_2026_DIR / "fantasypros_2025_ppr.json").read_text())
    current_players = resolve_players(live_raw, metadata_raw, parse_fantasypros_history(fantasypros_raw))

    profiles = profiles.copy()
    profiles["normalized_name"] = profiles["display_name"].map(normalize_name)
    draft_2026 = draft[(draft["season"] == 2026) & (draft["position"].isin(POSITIONS))].copy()
    draft_2026["normalized_name"] = draft_2026["pfr_player_name"].map(normalize_name)
    rookie_features = ["log_draft_pick", "age"] + TEAM_FEATURES

    forecast_rows: list[dict[str, Any]] = []
    for player in current_players:
        if player["position"] not in POSITIONS:
            continue
        position = player["position"]
        profile = resolve_nflverse_profile(player["player"], position, profiles)
        target_team = "LA" if player["team"] == "LAR" else player["team"]
        environment = team_environment.get(target_team, team_forecast(team_history, target_team, 2025))
        status = "unmodeled"
        reason = "No reliable NFLverse player match; Sleeper only"
        confidence = "Low"
        independent_points = np.nan
        independent_ppg = np.nan
        projected_games = np.nan
        components: dict[str, float] = {}
        origin: pd.Series | None = None

        rookie_match = draft_2026[(draft_2026["normalized_name"] == normalize_name(player["player"])) & (draft_2026["position"] == position)]
        if not rookie_match.empty:
            rookie = rookie_match.iloc[0]
            row = {
                "log_draft_pick": math.log1p(max(1, float(rookie["pick"]))),
                "age": float(rookie["age"]) if pd.notna(rookie["age"]) else 22.0,
                **{key: environment[key] for key in TEAM_FEATURES},
            }
            X = pd.DataFrame([row])[rookie_features]
            independent_points = max(0.0, float(rookie_models[position]["points"].predict(X)[0]))
            projected_games = float(np.clip(rookie_models[position]["games"].predict(X)[0], 1, 17))
            independent_ppg = independent_points / projected_games
            independent_points = independent_ppg * 17
            status = "rookie"
            confidence = "Low"
            reason = f"Rookie model: pick {int(rookie['pick'])}, age and destination-team environment"
        elif profile is not None:
            X, origin = current_feature_row(player, profile, history, team_history)
            if not X.empty:
                model = models[position]
                independent_ppg = max(0.0, float(model.ppg.predict(X[ppg_features_by_position[position]])[0]))
                raw_games = float(np.clip(model.games.predict(X[features])[0], 0, 17))
                # Walk-forward testing favored 75% of the player model plus a
                # 25% active-player prior of 14 games over either input alone.
                projected_games = float(np.clip(0.75 * raw_games + 0.25 * 14.0, 1, 17))
                components = {
                    component: max(0.0, float(component_model.predict(X[features])[0]))
                    for component, component_model in model.components.items()
                }
                component_ppg = max(0.0, component_fantasy_ppg(position, components))
                # Direct PPG is historically evaluated; components keep the football explanation auditable.
                independent_points = independent_ppg * 17
                status = "veteran"
                gap = int(X.iloc[0]["gap_years"])
                prior_games = float(origin["games"])
                if gap == 1 and prior_games >= 12 and pd.notna(origin.get("prev_fantasy_ppg")):
                    confidence = "High"
                elif gap <= 2 and prior_games >= 6:
                    confidence = "Medium"
                else:
                    confidence = "Low"
                team_note = "new team" if bool(X.iloc[0]["team_change"]) else "same team"
                reason = f"Veteran model: {int(origin['season'])} form, prior-year trend and {team_note} pass/run forecast"
                components["component_ppg"] = component_ppg

        pass_rank = int(environment.get("team_pass_rank", 16))
        rush_rank = int(environment.get("team_rush_rank", 16))
        reason = f"{reason}; team pass volume #{pass_rank}, rush volume #{rush_rank}"

        sleeper_points = float(player.get("projected_points") or 0.0)
        if pd.isna(independent_points):
            independent_points = sleeper_points
            independent_ppg = sleeper_points / 17
            projected_games = 17.0
            independent_weight = 0.0
        else:
            independent_weight = {"High": 0.65, "Medium": 0.50, "Low": 0.25}[confidence]
        decision_points = independent_weight * independent_points + (1 - independent_weight) * sleeper_points
        expected_points = independent_ppg * projected_games
        forecast_rows.append(
            {
                "player_id": player.get("player_id"),
                "player": player["player"],
                "position": position,
                "team": player["team"],
                "bye": player["bye"],
                "injury": player.get("injury") or "",
                "adp": float(player["adp"]),
                "sleeper_points": round(sleeper_points, 1),
                "sleeper_ppg_17": round(sleeper_points / 17, 2),
                "independent_points": round(float(independent_points), 1),
                "independent_ppg": round(float(independent_ppg), 2),
                "independent_expected_points": round(float(expected_points), 1),
                "projected_games": round(float(projected_games), 1),
                "projection_gap": round(float(independent_points - sleeper_points), 1),
                "decision_points": round(float(decision_points), 1),
                "decision_ppg_17": round(float(decision_points / 17), 2),
                "independent_weight": independent_weight,
                "confidence": confidence,
                "model_source": status,
                "reason": reason,
                "team_pass_rank": pass_rank,
                "team_rush_rank": rush_rank,
                "team_pass_rate": round(float(environment.get("next_team_pass_rate", 0.57)), 3),
                "own_pass_attempts": round(float(components.get("pass_attempts_pg", 0.0) * 17), 1) if position == "QB" else None,
                "sleeper_pass_attempts": player.get("pass_attempts"),
                "own_targets": round(float(components.get("targets_pg", 0.0) * 17), 1) if position != "QB" else None,
                "sleeper_targets": player.get("targets"),
                "own_carries": round(float(components.get("carries_pg", 0.0) * 17), 1),
                "sleeper_carries": player.get("rush_attempts"),
                "latest_history_season": int(origin["season"]) if origin is not None else None,
                "latest_history_games": int(origin["games"]) if origin is not None else None,
                "latest_history_ppg": round(float(origin["fantasy_ppg"]), 2) if origin is not None else None,
                **{key: round(value, 3) for key, value in components.items()},
            }
        )

    forecast = pd.DataFrame(forecast_rows).sort_values("adp").reset_index(drop=True)
    forecast.to_csv(OUTPUT_DIR / "independent_forecast.csv", index=False)
    team_2026_df.to_csv(OUTPUT_DIR / "team_forecast_2026.csv", index=False)

    overall = backtest_summary.groupby(["position", "model"], as_index=False).agg(
        seasons=("season", "nunique"), players=("players", "sum"), mae=("mae", "mean"), rank_correlation=("rank_correlation", "mean")
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "forecast_target": "next-season PPR points per game and games played",
            "training_seasons": [2015, 2025],
            "backtest_seasons": [2021, 2025],
            "team_environment": "Three-year weighted destination-team forecast, shrunk 20% to league average",
            "model": "Position-specific ridge regression with median imputation and standardized features",
            "sleeper_used_as_feature": False,
            "decision_blend": {"High": 0.65, "Medium": 0.50, "Low": 0.25, "Unmodeled": 0.0},
        },
        "sources": [PLAYER_SOURCE, TEAM_SOURCE, PLAYERS_SOURCE, DRAFT_SOURCE],
        "backtest_overall": overall.round(4).to_dict(orient="records"),
        "players": forecast.astype(object).where(pd.notna(forecast), None).to_dict(orient="records"),
    }
    (OUTPUT_DIR / "independent_forecast.json").write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")

    print(f"Transitions: {len(transitions):,}")
    print(f"Forecast players: {len(forecast):,}")
    print(f"Model sources: {forecast['model_source'].value_counts().to_dict()}")
    print("Backtest summary:")
    print(overall.round(3).to_string(index=False))
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
