# Fantasy Football Model: Agent Guide

This file is the shared operating guide for coding agents working in this repository. Keep it tool-neutral: Codex, Claude Code, and other agents should follow the same rules.

## Project purpose

This project turns exported FantasyPros player statistics into position-specific fantasy-football rankings. Historical notebooks calculate relationships between real-game box-score statistics and fantasy production, use those relationships to build a score, and export a ranked Excel workbook.

The immediate product is a draft-decision aid, not a general-purpose machine-learning platform. Prefer a small, auditable workflow over extra infrastructure. Historical work is stored in Jupyter notebooks, but new production work should be script-first and should not require Jupyter.

## User and communication style

The owner is product- and data-oriented, technically curious, and not a professional software developer.

- Lead with the practical outcome.
- Explain important technical ideas in plain language without talking down to the user.
- Before a non-trivial change, state the plan and any meaningful tradeoff.
- After a change, explain what changed, why it matters, and what could break later.
- Keep the implementation simple. Apply YAGNI: do not add abstractions or tools until the project needs them.

## Repository map

- `QB/`, `RB/`, `WR/`, `TE/`: position-specific models.
- `<position>/<year>/*_Data_<year>.xlsx`: model input for that draft-year folder. Older folders sometimes omit the year suffix.
- `<position>/<year>/*_Model_<year>.ipynb`: executable Jupyter notebook. Older folders sometimes use `*_Model.ipynb`.
- `<position>/<year>/*_Analysis.xlsx`: generated ranking output.
- `<position>/Weeks/`: older in-season, week-by-week experiments. Treat these as historical until repaired and verified.
- `scripts/download_nflverse_data.py`: reproducible downloader for public 2015–2025 NFLverse inputs.
- `scripts/build_independent_forecast.py`: time-ordered independent forecast and walk-forward backtest.
- `scripts/build_2026_draft_data.py`: league-specific VBD, market comparison, CSV/JSON, and HTML report.
- `scripts/audit_2026_outputs.py`: generated-data contract checks.
- `scripts/build_2026_draft_board.mjs`: Excel presentation layer using the Codex spreadsheet runtime.

Notebook paths are relative to their own folder. Run a notebook with its position/year directory as the working directory.

## Current model generations

- 2023 notebooks: correlation-weighted composite scores, calculated and evaluated on the same data.
- 2024 notebooks: correlation-derived features plus Ridge and Random Forest models predicting `FPTS/G`, with a train/test split.
- 2025 RB and WR notebooks: composite-score workflow followed by a model trained to reproduce that composite. These need validation before being treated as predictive rankings.
- 2026 script workflow: position-specific next-season Ridge forecasts trained on 2015–2025 NFLverse data, with destination-team context, walk-forward evaluation, expected games, and league-specific VBD. Sleeper projections and ADP are excluded from the independent forecast and used only afterward for decision blending and market comparison.

Do not assume the newest notebook is automatically the best starting point. Preserve historical files and make new draft-year work in a new year folder unless the user explicitly asks to alter history.

## Data and metric rules

- Confirm the fantasy scoring format before interpreting or publishing a ranking (PPR, half-PPR, standard, superflex, bonuses, etc.). FantasyPros exports can differ by scoring setup.
- Record what season the statistics describe and what draft season the output targets. A folder named for a draft year may contain the prior NFL season's results.
- Treat `FPTS` and `FPTS/G` as outcomes, not independent football inputs. Including either in features used to predict that same outcome is target leakage unless the purpose is explicitly descriptive.
- Correlation is descriptive, not automatically predictive or causal. A useful backtest must train on earlier data and evaluate on later, unseen data.
- Do not square a negative correlation and then apply it as a positive contribution without preserving the direction of the relationship.
- Put inputs on comparable scales before averaging them. Raw yards, touchdowns, targets, and rates have different units; averaging unscaled values lets large-number columns dominate.
- Compare rankings with draft-market context such as ADP or expert consensus. The actionable output is usually value above/below market, not an isolated rank.
- Keep missing players and missing stats visible. Do not silently convert unknown projections to zero when zero means actual expected production.

## Safe workflow

1. Inspect `git status` and preserve unrelated user changes.
2. Inspect the source workbook's sheets, headers, row counts, and scoring assumptions before changing code.
3. Work in a new year folder for a new draft cycle. Do not overwrite historical inputs or analyses.
4. Keep raw downloaded data separate from derived output when introducing a new workflow.
5. Run notebooks or scripts on a copy or in the new year folder first; existing notebooks overwrite their `*_Analysis.xlsx` files.
6. Validate representative player calculations, missing values, duplicate players, row counts, and final rank uniqueness.
7. Report model quality with an out-of-sample comparison and a simple baseline. Never describe in-sample fit as forecast accuracy.
8. Before handing off, run the relevant notebook end to end and review the exported workbook.

For new work, replace "notebook" in the steps above with the relevant script. The preferred user-facing outputs are:

- an Excel draft board for filtering, sorting, and use during the draft;
- a self-contained HTML report for explanation, diagnostics, and quick visual review.

Do not require the user to open a notebook to understand or use a result.

## Environment

Use Python 3.11 or newer and install `requirements.txt` in a local virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Jupyter and Matplotlib are intentionally optional. Install `requirements-notebooks.txt` only when reproducing or investigating a historical notebook:

```bash
python -m pip install -r requirements-notebooks.txt
```

Historical notebooks use relative paths, so their working directory must be the folder containing the notebook and its input workbook.

## Current end-to-end workflow

```bash
python scripts/download_nflverse_data.py
python scripts/build_independent_forecast.py
python scripts/build_2026_draft_data.py
python scripts/audit_2026_outputs.py
```

The downloader is safe to rerun: it keeps existing files unless `--force` is supplied. The live Sleeper files are separate local inputs and are intentionally ignored because they contain league-specific state. If a Sleeper statistic is shown as a dash, preserve it as unknown; do not silently replace it with zero.

## Change boundaries

- Do not commit, push, publish, or download fresh third-party data unless the user asks.
- Do not rewrite all notebooks merely to remove duplication during urgent draft preparation.
- Prefer a clear Python module or script for new reusable logic. Treat notebooks as historical exploration and optional review aids.
- If changing model logic, retain a baseline and document the before/after ranking and evaluation effect.
- Do not add secrets, credentials, personal league exports, or private draft results to Git.

## Completion standard

A model change is complete only when the environment is reproducible, the input contract is documented, the calculation runs end to end, the ranking is checked against a baseline on unseen data, and the exported output can be understood without reading notebook internals.
