#!/usr/bin/env python3
"""Build the 2026 draft data and HTML report from captured source JSON.

This is intentionally a transparent value-based draft model, not a machine-
learning forecast. Sleeper's current projections are converted to value over
replacement using this league's actual starter and FLEX configuration.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "2026"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "2026"
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.lower()
    value = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", value)
    return re.sub(r"[^a-z0-9]", "", value)


def abbreviated_name(player: dict[str, Any]) -> str:
    first = (player.get("first_name") or "").strip()
    last = (player.get("last_name") or "").strip()
    return normalize_name((first[:1] + last) if first else last)


def to_number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except ValueError:
        return None


def parse_fantasypros_history(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    history: dict[str, dict[str, Any]] = {}
    for position, payload in raw["positions"].items():
        headers = payload["headers"]
        idx = {name: headers.index(name) for name in ("Rank", "Player", "G", "FPTS", "FPTS/G")}
        for row in payload["rows"]:
            player_text = row[idx["Player"]]
            match = re.match(r"^(.*?)\s+\(([A-Z]+)\)$", player_text)
            full_name = match.group(1) if match else player_text
            team = match.group(2) if match else ""
            history[normalize_name(full_name)] = {
                "position": position,
                "team_2025": team,
                "rank_2025": int(float(row[idx["Rank"]])),
                "games_2025": int(float(row[idx["G"]])),
                "points_2025": to_number(row[idx["FPTS"]]),
                "ppg_2025": to_number(row[idx["FPTS/G"]]),
            }
    return history


def parse_position_text(value: str) -> tuple[str, str, int] | None:
    match = re.match(r"^(QB|RB|WR|TE|K|DEF) - ([A-Z]+)\((\d+)\)$", value or "")
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3))


def resolve_players(
    live_raw: dict[str, Any],
    metadata_raw: dict[str, dict[str, Any]],
    history: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    metadata_index: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for player in metadata_raw.values():
        position = player.get("position")
        team = player.get("team")
        if position and team:
            metadata_index[(position, team, abbreviated_name(player))].append(player)

    prepared: list[dict[str, Any]] = []
    grouped_rows: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for source_row in live_raw["rows"]:
        parsed = parse_position_text(source_row.get("positionText", ""))
        if not parsed:
            continue
        position, team, bye = parsed
        cells = source_row.get("cells", [])
        if len(cells) != len(live_raw["columns"]):
            continue
        row = {
            "source_name": source_row.get("name", ""),
            "position": position,
            "team": team,
            "bye": bye,
            "injury": source_row.get("injury", ""),
            **{column: to_number(value) for column, value in zip(live_raw["columns"], cells)},
        }
        row["adp"] = row["adp"] if row["adp"] is not None else 999.0
        row["source_order"] = int(str(source_row.get("top", "0px")).replace("px", ""))
        key = (position, team, normalize_name(row["source_name"]))
        grouped_rows[key].append(row)

    for key, rows in grouped_rows.items():
        position, team, _ = key
        candidates = metadata_index.get(key, [])
        rows.sort(key=lambda row: (row["adp"], row["source_order"]))
        candidates.sort(
            key=lambda player: (
                -(history.get(normalize_name(player.get("full_name") or ""), {}).get("ppg_2025") or -1),
                player.get("full_name") or "",
            )
        )
        for index, row in enumerate(rows):
            player = candidates[index] if index < len(candidates) else None
            if player:
                row["player_id"] = player.get("player_id")
                row["player"] = player.get("full_name") or row["source_name"]
            else:
                row["player_id"] = None
                row["player"] = row["source_name"].replace(".", "") if position == "DEF" else row["source_name"]
            row.update(history.get(normalize_name(row["player"]), {}))
            prepared.append(row)

    prepared.sort(key=lambda row: (row["adp"], row["source_order"]))
    return prepared


def calculate_replacement_values(
    players: list[dict[str, Any]], draft: dict[str, Any], points_key: str = "projected_points"
) -> tuple[dict[str, int], dict[str, float], dict[str, int]]:
    settings = draft["settings"]
    teams = int(settings["teams"])
    base_starters = {
        "QB": teams * int(settings.get("slots_qb", 0)),
        "RB": teams * int(settings.get("slots_rb", 0)),
        "WR": teams * int(settings.get("slots_wr", 0)),
        "TE": teams * int(settings.get("slots_te", 0)),
    }
    flex_slots = teams * int(settings.get("slots_flex", 0))

    by_position: dict[str, list[dict[str, Any]]] = {}
    used_ids: set[str] = set()
    for position in SKILL_POSITIONS:
        ranked = sorted(
            [p for p in players if p["position"] == position and p.get(points_key) is not None],
            key=lambda p: (-p[points_key], p["adp"]),
        )
        by_position[position] = ranked
        for player in ranked[: base_starters[position]]:
            if player.get("player_id"):
                used_ids.add(str(player["player_id"]))

    flex_pool = sorted(
        [
            player
            for position in ("RB", "WR", "TE")
            for player in by_position[position]
            if str(player.get("player_id")) not in used_ids
        ],
        key=lambda p: (-p[points_key], p["adp"]),
    )[:flex_slots]
    flex_allocation = {position: 0 for position in SKILL_POSITIONS}
    for player in flex_pool:
        flex_allocation[player["position"]] += 1

    replacement_ranks: dict[str, int] = {}
    replacement_points: dict[str, float] = {}
    for position in SKILL_POSITIONS:
        starter_count = base_starters[position] + flex_allocation[position]
        replacement_rank = starter_count + 1
        replacement_ranks[position] = replacement_rank
        position_players = by_position[position]
        reference_index = min(replacement_rank - 1, len(position_players) - 1)
        replacement_points[position] = float(position_players[reference_index][points_key])
    return replacement_ranks, replacement_points, flex_allocation


def add_model_fields(
    players: list[dict[str, Any]],
    replacement_ranks: dict[str, int],
    replacement_points: dict[str, float],
) -> list[dict[str, Any]]:
    skill_players = [p for p in players if p["position"] in SKILL_POSITIONS]
    for position in SKILL_POSITIONS:
        ranked = sorted(
            [p for p in skill_players if p["position"] == position],
            key=lambda p: (-(p["projected_points"] or -999), p["adp"]),
        )
        starter_count = max(1, replacement_ranks[position] - 1)
        for rank, player in enumerate(ranked, start=1):
            player["position_rank"] = rank
            replacement_ppg = replacement_points[position] / 17
            projected_ppg = (player["projected_points"] or 0) / 17
            expected_games = float(player.get("projected_games") or 17)
            # A missed game costs the player's advantage over a replacement,
            # not an entire lineup slot: a bench/waiver substitute can play.
            player["vbd"] = round((projected_ppg - replacement_ppg) * expected_games, 1)
            if rank <= max(1, round(starter_count * 0.20)):
                player["tier"] = "Elite"
            elif rank <= max(2, round(starter_count * 0.50)):
                player["tier"] = "Strong starter"
            elif rank <= starter_count:
                player["tier"] = "Starter"
            else:
                player["tier"] = "Depth"

    model_sorted = sorted(skill_players, key=lambda p: (-p["vbd"], p["adp"]))
    for rank, player in enumerate(model_sorted, start=1):
        player["model_rank"] = rank
        player["market_gap"] = round(player["adp"] - rank, 1)
        player["round"] = math.ceil(player["adp"] / 12)
        player["projected_ppg_17"] = round((player["projected_points"] or 0) / 17, 1)
        if player["vbd"] <= 0:
            player["signal"] = "Depth"
        elif player["market_gap"] >= 15:
            player["signal"] = "Target"
        elif player["market_gap"] >= 7:
            player["signal"] = "Value"
        elif player["market_gap"] <= -15:
            player["signal"] = "Pricey"
        elif player["market_gap"] <= -7:
            player["signal"] = "Slight reach"
        else:
            player["signal"] = "Fair"
    return model_sorted


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def table_html(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    body_rows = []
    for row in rows:
        cells = []
        for key, _ in columns:
            value = row.get(key, "")
            if value is None:
                display = "-"
            elif isinstance(value, float):
                display = f"{value:.1f}"
            else:
                display = str(value)
            classes = []
            if key == "signal":
                classes.extend(["signal", display.lower().replace(" ", "-")])
            if key in {"position", "adp_position_label", "decision_position_label"}:
                position = display.split()[0].lower()
                if position in {"qb", "rb", "wr", "te"}:
                    classes.extend(["position", f"pos-{position}"])
            css_class = f' class="{" ".join(classes)}"' if classes else ""
            cells.append(f"<td{css_class}>{html.escape(display)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def write_html(
    path: Path,
    model_sorted: list[dict[str, Any]],
    draft: dict[str, Any],
    replacement_ranks: dict[str, int],
    replacement_points: dict[str, float],
    flex_allocation: dict[str, int],
    extracted_at: str,
    independent: dict[str, Any],
) -> None:
    market_sorted = sorted(model_sorted, key=lambda p: (p["adp"], p["model_rank"]))
    cheat_pages = []
    for page_number, page_start in enumerate(range(0, len(market_sorted), 80), start=1):
        page_players = market_sorted[page_start:page_start + 80]
        panels = []
        for panel_start in (0, 40):
            panel_players = page_players[panel_start:panel_start + 40]
            if panel_players:
                panels.append(
                    table_html(
                        panel_players,
                        [
                            ("adp", "ADP"),
                            ("player", "Player"),
                            ("adp_position_label", "ADP Pos"),
                            ("team", "Team"),
                            ("model_rank", "Decision"),
                            ("market_gap", "Gap"),
                        ],
                    )
                )
        first_adp = page_players[0]["adp"]
        last_adp = page_players[-1]["adp"]
        cheat_pages.append(
            f'<div class="cheat-page"><h3>Page {page_number}: ADP {first_adp:.1f}-{last_adp:.1f}</h3>'
            f'<div class="cheat-panels">{"".join(panels)}</div></div>'
        )
    bargains = sorted(
        [p for p in model_sorted if p["adp"] <= 180 and p["vbd"] > 0],
        key=lambda p: (-p["market_gap"], p["adp"]),
    )[:20]
    pricey = sorted(
        [p for p in model_sorted if p["adp"] <= 120 and p["vbd"] > 0],
        key=lambda p: (p["market_gap"], p["adp"]),
    )[:15]
    top_model = model_sorted[:40]
    backtest = independent.get("backtest_overall", [])
    selected_models = {"QB": "team_model_ppg", "RB": "player_only_ppg", "WR": "team_model_ppg", "TE": "team_model_ppg"}
    accuracy_rows = []
    for position in SKILL_POSITIONS:
        chosen = next((row for row in backtest if row["position"] == position and row["model"] == selected_models[position]), None)
        baseline = next((row for row in backtest if row["position"] == position and row["model"] == "prior_year_ppg"), None)
        if chosen and baseline:
            accuracy_rows.append({
                "position": position,
                "model": "Team-aware ridge" if selected_models[position] == "team_model_ppg" else "Player-only ridge",
                "players": int(chosen["players"]),
                "model_mae": float(chosen["mae"]),
                "baseline_mae": float(baseline["mae"]),
                "rank_correlation": float(chosen["rank_correlation"]),
            })
    position_sections = []
    for position in SKILL_POSITIONS:
        rows = sorted(
            [p for p in model_sorted if p["position"] == position],
            key=lambda p: p["position_rank"],
        )[:20]
        position_sections.append(
            f"<section><h2>{position} board</h2>"
            + table_html(
                rows,
                [
                    ("position_rank", "Pos Rank"),
                    ("player", "Player"),
                    ("team", "Team"),
                    ("bye", "Bye"),
                    ("independent_points", "Our 17G"),
                    ("sleeper_projected_points", "Sleeper"),
                    ("projection_gap", "Proj Gap"),
                    ("projected_games", "Exp G"),
                    ("vbd", "VBD"),
                    ("adp", "ADP"),
                    ("market_gap", "Gap"),
                    ("tier", "Tier"),
                ],
            )
            + "</section>"
        )

    settings = draft["settings"]
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    replacement_cards = "".join(
        f'<div class="card"><span>{position} replacement</span><strong>{replacement_ranks[position]}</strong>'
        f'<small>{replacement_points[position]:.1f} projected points</small></div>'
        for position in SKILL_POSITIONS
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>2026 Fantasy Draft Board</title>
<style>
:root{{--ink:#172033;--muted:#667085;--line:#d9dee8;--navy:#172b4d;--blue:#dce9ff;--green:#d9f3e5;--red:#ffe0dd;--gold:#fff0c2;--qb:#ea9999;--rb:#b7e1cd;--wr:#a4c2f4;--te:#ffe599;}}
*{{box-sizing:border-box}} body{{margin:0;background:#f4f6fa;color:var(--ink);font:14px/1.45 Inter,Arial,sans-serif}}
main{{max-width:1240px;margin:0 auto;padding:36px 24px 72px}} h1{{font-size:32px;margin:0 0 8px}} h2{{margin:34px 0 12px;font-size:21px}}
.lede{{color:var(--muted);font-size:16px;max-width:850px}} .meta{{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);margin:16px 0 26px}}
.cards{{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px}} .card{{background:white;border:1px solid var(--line);border-radius:10px;padding:15px}}
.card span,.card small{{display:block;color:var(--muted)}} .card strong{{display:block;font-size:27px;margin:3px 0}}
.note{{background:#eef4ff;border-left:4px solid #4b7bec;padding:14px 16px;margin:22px 0;border-radius:4px}}
.table-wrap,section{{overflow:auto}} table{{width:100%;border-collapse:separate;border-spacing:0;background:white;border:1px solid var(--line);border-radius:8px;overflow:hidden}}
th{{position:sticky;top:0;background:var(--navy);color:white;text-align:left;padding:9px 10px;white-space:nowrap}} td{{padding:8px 10px;border-top:1px solid #edf0f5;white-space:nowrap}}
tbody tr:hover{{background:#f7f9fc}} .signal{{font-weight:700}} .target,.value{{background:var(--green)}} .pricey,.slight-reach{{background:var(--red)}} .fair{{background:var(--blue)}} .depth{{background:#f1f2f4}}
.position{{font-weight:700;text-align:center}} .pos-qb{{background:var(--qb)}} .pos-rb{{background:var(--rb)}} .pos-wr{{background:var(--wr)}} .pos-te{{background:var(--te)}}
.legend{{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 14px}} .legend span{{padding:5px 10px;border-radius:4px;font-weight:700}}
.cheat-page{{break-inside:avoid;margin:0 0 24px}} .cheat-page h3{{margin:12px 0 8px}} .cheat-panels{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .cheat-panels td,.cheat-panels th{{padding:6px 8px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:22px}} footer{{margin-top:40px;color:var(--muted);font-size:12px}}
@media(max-width:850px){{.cards,.two,.cheat-panels{{grid-template-columns:1fr}} main{{padding:24px 12px}}}}
@media print{{body{{background:white}} main{{max-width:none;padding:0}} .cheat-page{{break-after:page}} .cheat-page:last-child{{break-after:auto}}}}
</style></head><body><main>
<h1>2026 Fantasy Draft Board</h1>
<p class="lede">A 12-team PPR, one-QB board built from an independent 2015–2025 NFL history model, destination-team pass/run environment, expected availability, and live Sleeper ADP. Sleeper projections are comparison and blending inputs—not features in the independent forecast.</p>
<div class="meta"><span>Generated {generated}</span><span>16 rounds</span><span>1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX</span><span>Source capture {html.escape(extracted_at)}</span></div>
<div class="cards">{replacement_cards}</div>
<div class="note"><strong>How to use it:</strong> Proj Gap compares our independent 17-game pace with Sleeper. Positive draft Gap means the risk-adjusted decision rank is earlier than Sleeper ADP. Expected games reduces only the points above a replacement player because you can substitute during missed weeks. Use ADP as price, not as truth. FLEX allocation: {flex_allocation['RB']} RB, {flex_allocation['WR']} WR, {flex_allocation['TE']} TE.</div>
<section id="cheat-sheet"><h2>Primary draft cheat sheet</h2><p>Sorted by Sleeper ADP so you can find players quickly. The colored label is the player's market rank within the position, matching your prior printout. Decision is our league-adjusted overall rank; a positive Gap means our model would take the player earlier than the market.</p><div class="legend"><span class="pos-wr">Wide receiver</span><span class="pos-rb">Running back</span><span class="pos-te">Tight end</span><span class="pos-qb">Quarterback</span></div>{''.join(cheat_pages)}</section>
<section><h2>Top decision board</h2>{table_html(top_model, [('model_rank','Model'),('adp','ADP'),('market_gap','Draft Gap'),('player','Player'),('decision_position_label','Model Pos'),('team','Team'),('independent_points','Our 17G'),('sleeper_projected_points','Sleeper'),('projection_gap','Proj Gap'),('projected_games','Exp G'),('confidence','Conf'),('vbd','VBD'),('signal','Signal')])}</section>
<div class="two"><section><h2>Potential values</h2>{table_html(bargains,[('adp','ADP'),('model_rank','Model'),('market_gap','Draft Gap'),('player','Player'),('adp_position_label','ADP Pos'),('independent_points','Our 17G'),('sleeper_projected_points','Sleeper'),('projection_gap','Proj Gap'),('confidence','Conf')])}</section>
<section><h2>Potential reaches</h2>{table_html(pricey,[('adp','ADP'),('model_rank','Model'),('market_gap','Draft Gap'),('player','Player'),('adp_position_label','ADP Pos'),('independent_points','Our 17G'),('sleeper_projected_points','Sleeper'),('projection_gap','Proj Gap'),('confidence','Conf')])}</section></div>
{''.join(position_sections)}
<section><h2>Walk-forward validation</h2><p>Each test season was predicted only from earlier seasons. MAE is average absolute PPR points-per-game error; lower is better. Rank correlation measures ordering; higher is better.</p>{table_html(accuracy_rows,[('position','Pos'),('model','Selected'),('players','Tests'),('model_mae','Model MAE'),('baseline_mae','Repeat-last-year MAE'),('rank_correlation','Rank corr')])}</section>
<section><h2>Method and limitations</h2><p>The independent model uses position-specific ridge regression. Inputs include prior player volume, efficiency, age, experience, draft capital, prior-year trend and a three-year destination-team pass/run forecast. Sleeper projection and ADP are excluded from model training. The decision forecast blends the independent forecast with Sleeper according to evidence confidence: 65% independent for high confidence, 50% for medium, and 25% for low-confidence rookies or sparse histories.</p><p>VBD is points above the replacement player during expected active games. Required starters are filled first, then the highest projected remaining RB/WR/TE players fill FLEX. The model beat repeating last year's PPG for QB, RB and WR in 2021–2025 walk-forward tests; TE was effectively tied, so TE disagreements deserve more caution.</p><p>This remains uncertain. Coaching changes are represented only indirectly through regression toward league average; rookies use draft capital, age and team environment because they have no NFL production; injuries and depth-chart changes can move quickly. Kicker and defense are intentionally excluded from the skill-position model.</p></section>
<footer>Sources: NFLverse regular-season player/team summaries, player registry and draft picks; Sleeper live PPR projections, ADP and league settings; FantasyPros 2025 PPR results for display context. League: {html.escape(draft.get('metadata', {}).get('name',''))}. Teams: {settings.get('teams')}.</footer>
</main></body></html>"""
    path.write_text(document, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    fantasypros = json.loads((RAW_DIR / "fantasypros_2025_ppr.json").read_text())
    live = json.loads((RAW_DIR / "sleeper_live_2026.json").read_text())
    metadata = json.loads((RAW_DIR / "sleeper_players.json").read_text())
    draft = json.loads((RAW_DIR / "sleeper_draft_2026.json").read_text())
    independent = json.loads((output_dir / "independent_forecast.json").read_text())

    history = parse_fantasypros_history(fantasypros)
    all_players = resolve_players(live, metadata, history)
    forecast_index = {
        (normalize_name(row["player"]), row["position"]): row
        for row in independent["players"]
    }
    for player in all_players:
        player["sleeper_projected_points"] = player.get("projected_points")
        forecast = forecast_index.get((normalize_name(player["player"]), player["position"]))
        if forecast:
            for key, value in forecast.items():
                if key not in {"player", "player_id", "position", "team", "bye", "adp", "injury"}:
                    player[key] = value
            player["projected_points"] = forecast["decision_points"]
            player["sleeper_projected_points"] = forecast["sleeper_points"]
            player["projected_games"] = forecast["projected_games"]
        else:
            player["independent_points"] = player.get("projected_points")
            player["independent_ppg"] = (player.get("projected_points") or 0) / 17
            player["decision_points"] = player.get("projected_points")
            player["projected_games"] = 17.0
            player["confidence"] = "Low"
            player["model_source"] = "unmodeled"
            player["reason"] = "No independent forecast match"
    replacement_ranks, replacement_points, flex_allocation = calculate_replacement_values(all_players, draft)
    model_sorted = add_model_fields(all_players, replacement_ranks, replacement_points)
    independent_replacement_ranks, independent_replacement_points, independent_flex_allocation = calculate_replacement_values(
        all_players, draft, "independent_points"
    )
    for player in model_sorted:
        replacement_ppg = independent_replacement_points[player["position"]] / 17
        player["independent_vbd"] = round(
            (player["independent_points"] / 17 - replacement_ppg) * player["projected_games"], 1
        )
    independent_sorted = sorted(model_sorted, key=lambda p: (-p["independent_vbd"], p["adp"]))
    for rank, player in enumerate(independent_sorted, start=1):
        player["independent_rank"] = rank
        player["independent_market_gap"] = round(player["adp"] - rank, 1)

    skill_adp = sorted(model_sorted, key=lambda p: (p["adp"], p["model_rank"]))
    adp_position_counts = {position: 0 for position in SKILL_POSITIONS}
    for player in skill_adp:
        position = player["position"]
        adp_position_counts[position] += 1
        player["adp_position_rank"] = adp_position_counts[position]
        player["adp_position_label"] = f"{position} {player['adp_position_rank']}"
        player["decision_position_label"] = f"{position} {player['position_rank']}"
    other_players = sorted(
        [p for p in all_players if p["position"] not in SKILL_POSITIONS],
        key=lambda p: p["adp"],
    )
    with (output_dir / "team_forecast_2026.csv").open(encoding="utf-8") as file:
        team_forecast_rows = []
        for row in csv.DictReader(file):
            team_forecast_rows.append(
                {key: (value if key == "team" else float(value)) for key, value in row.items()}
            )
    columns = [
        "model_rank", "independent_rank", "adp", "market_gap", "independent_market_gap", "round", "player", "position", "position_rank",
        "adp_position_rank", "adp_position_label", "decision_position_label",
        "team", "bye", "injury", "tier", "signal", "projected_points", "projected_ppg_17",
        "independent_points", "independent_ppg", "independent_expected_points",
        "sleeper_projected_points", "sleeper_ppg_17", "projection_gap", "projected_games",
        "confidence", "model_source", "reason", "team_pass_rank", "team_rush_rank", "team_pass_rate",
        "own_pass_attempts", "sleeper_pass_attempts", "own_targets", "sleeper_targets", "own_carries", "sleeper_carries",
        "vbd", "independent_vbd", "games_2025", "points_2025", "ppg_2025", "rank_2025", "player_id",
        "rush_attempts", "rush_yards", "rush_touchdowns", "receptions", "targets",
        "receiving_yards", "receiving_touchdowns", "completions", "pass_attempts",
        "pass_yards", "pass_touchdowns",
    ]
    write_csv(output_dir / "draft_board.csv", skill_adp, columns)
    write_csv(
        output_dir / "kicker_defense.csv",
        other_players,
        ["adp", "player", "position", "team", "bye", "injury", "projected_points", "player_id"],
    )

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "sources": {
            "sleeper_live": live.get("extractedAt"),
            "fantasypros_live": fantasypros.get("extractedAt"),
        },
        "league": {"teams": draft["settings"]["teams"], "rounds": draft["settings"]["rounds"], "scoring": "PPR"},
        "replacement_ranks": replacement_ranks,
        "replacement_points": replacement_points,
        "flex_allocation": flex_allocation,
        "independent_replacement_ranks": independent_replacement_ranks,
        "independent_replacement_points": independent_replacement_points,
        "independent_flex_allocation": independent_flex_allocation,
        "forecast_method": independent["method"],
        "backtest_overall": independent["backtest_overall"],
        "team_forecast": team_forecast_rows,
        "players_by_adp": skill_adp,
        "players_by_model": model_sorted,
        "players_by_independent": independent_sorted,
        "kicker_defense": other_players,
    }
    (output_dir / "draft_board_data.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_html(
        output_dir / "draft_report.html",
        model_sorted,
        draft,
        replacement_ranks,
        replacement_points,
        flex_allocation,
        live.get("extractedAt", ""),
        independent,
    )

    print(f"Players modeled: {len(model_sorted)}")
    print(f"K/DEF rows retained: {len(other_players)}")
    print(f"Replacement ranks: {replacement_ranks}")
    print(f"FLEX allocation: {flex_allocation}")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
