# Fantasy Football Draft Model

This repository contains both the original position-by-position fantasy-football experiments and a current, independent next-season forecast. The historical notebooks read FantasyPros exports and score players from relationships between football statistics and fantasy production. The 2026 workflow instead learns from one NFL season to predict the next, then exports an Excel draft board and HTML report.

The repository contains QB, RB, WR, and TE notebooks from several historical model generations. The current 2026 workflow is script-first and produces a league-specific draft board without Jupyter.

## How the repository is organized

Each position has year folders containing three main artifacts:

- `*_Data*.xlsx`: input player statistics.
- `*_Model*.ipynb`: historical Jupyter analysis.
- `*_Analysis.xlsx`: generated player ranking and supporting statistics.

The `Weeks` folders are older in-season experiments. Their notebook input filenames do not currently match the checked-in workbooks, so they should be treated as historical until repaired.

## Set up the project

Python 3.11 or newer is recommended. Jupyter is not required for current work.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

To open or reproduce the historical notebooks, install the optional environment:

```bash
python -m pip install -r requirements-notebooks.txt
jupyter lab
```

The historical notebooks use relative file paths and write directly to the adjacent `*_Analysis.xlsx` file. Use a disposable copy when investigating them so checked-in outputs are not overwritten.

## What the historical models did

The exact method varies by year:

- **2023:** Calculates correlations between box-score statistics and fantasy points per game, turns squared correlations into weights, and averages weighted statistics into a composite score.
- **2024:** Calculates weights on a training subset, then fits Ridge regression and Random Forest models to predict fantasy points per game on a held-out subset.
- **2025 RB/WR:** Builds a correlation-weighted composite, then fits models to reproduce that composite score.

These remain useful experiments, but most inputs and targets came from the same completed season. They are preserved as history rather than used as the current draft forecast.

## How the current forecast works

The 2026 forecast uses public NFLverse regular-season data from 2015 through 2025. For every veteran, a row from season A is used to predict season A+1. That time ordering matters: the model is tested on seasons it could not have seen yet, which is closer to the real draft problem.

- Separate Ridge models are fit for QB, RB, WR, and TE. Ridge is a conservative linear model that handles overlapping statistics without letting one noisy input dominate.
- Player inputs include prior volume, efficiency, age, experience, draft capital, trends, and whether the player changed teams.
- Destination-team passing and rushing environments use the prior three seasons, weighted 55% / 30% / 15%, then pulled 20% toward league average to avoid overreacting.
- Team context is used directly for QB, WR, and TE forecasts. A player-only RB points model performed slightly better in the walk-forward test, so RB points use that version while RB opportunity explanations still show team context.
- Sleeper projections and ADP are excluded from the independent model. They are added afterward to create a confidence-weighted decision ranking and reveal market disagreements.
- Value over replacement is tailored to this 12-team, full-PPR, one-QB league. It measures a player's expected points above the replacement-level option at that position.

Rookies are lower confidence because the current input set contains draft capital, age, and team environment but not college production or athletic testing.

## Direction for new work

New model logic should live in normal Python scripts rather than notebooks. The intended user-facing outputs are:

- an Excel draft board for filtering and sorting during a draft;
- a self-contained HTML report that explains the rankings and model checks.

The user should not need to read code or open Jupyter to use either output.

## Build the 2026 draft data

The raw NFLverse downloads and private Sleeper captures are intentionally ignored by Git. Download the reproducible public inputs once:

```bash
python scripts/download_nflverse_data.py
```

The current live Sleeper capture supplies 2026 PPR projections, ADP, injuries, and market opportunity where available. Because it is league-specific, it remains local under `data/raw/2026/`. The independent model does not train on those Sleeper numbers.

After activating the virtual environment, rebuild the independent forecast, decision data, and self-contained HTML report with:

```bash
python scripts/build_independent_forecast.py
python scripts/build_2026_draft_data.py
python scripts/audit_2026_outputs.py
```

Generated files go to `outputs/2026/`. The reviewed annual package in that folder is checked into Git so the exact draft board survives after the local checkout is removed. The key portable outputs are `draft_board_data.json`, `draft_board.csv`, `independent_forecast.csv`, `team_forecast_2026.csv`, the backtest CSVs, and `draft_report.html`. The Excel builder in `scripts/build_2026_draft_board.mjs` is an agent-side presentation step that uses the Codex spreadsheet runtime; the Python JSON remains the portable source of truth.

The current workbook is designed around the confirmed league settings: 12 teams, full PPR, one QB, two RB, two WR, one TE, one FLEX, kicker, defense, and no unusual bonuses. Change the league configuration in `scripts/build_2026_draft_data.py` before using it for a different format.

## Updating for a new draft cycle

Do not overwrite a historical year. A safe workflow is:

1. Confirm league scoring rules: PPR, half-PPR, standard, superflex, bonuses, roster size, and number of teams.
2. Create a new folder for the draft year under each needed position.
3. Save raw FantasyPros exports without editing them.
4. Transform raw exports into a documented model-input table.
5. Train only on seasons that occur before the season being evaluated.
6. Compare the model with a simple baseline and with current ADP.
7. Export a draft board showing model rank, market rank, and the gap between them.

## Agent instructions

Coding agents should read [`AGENTS.md`](AGENTS.md). Claude Code is pointed to the same shared guide through [`CLAUDE.md`](CLAUDE.md).
