import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, "..");
const dataDir = path.join(root, "outputs", "2026");
const outputDir = dataDir;
const previewDir = path.join(dataDir, "previews");
const data = JSON.parse(await fs.readFile(path.join(dataDir, "draft_board_data.json"), "utf8"));

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const wb = Workbook.create();
const navy = "#172B4D";
const ink = "#172033";
const muted = "#667085";
const light = "#F4F6FA";
const line = "#D9DEE8";
const white = "#FFFFFF";
const green = "#D9F3E5";
const red = "#FFE0DD";
const gold = "#FFF0C2";
const blue = "#DCE9FF";
// Exact fills extracted from the user's 2025 Sleeper ADP printout.
const positionColors = { QB: "#EA9999", RB: "#B7E1CD", WR: "#A4C2F4", TE: "#FFE599", K: "#D8CDF2", DEF: "#D6D8DC" };

function excelColumn(index) {
  let n = index + 1;
  let result = "";
  while (n > 0) {
    const remainder = (n - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    n = Math.floor((n - 1) / 26);
  }
  return result;
}

function rounded(value, decimals = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
  return Number(Number(value).toFixed(decimals));
}

function styleTitle(sheet, range, title, subtitle) {
  sheet.getRange(range).merge();
  const cell = sheet.getRange(range.split(":")[0]);
  cell.values = [[title]];
  cell.format = { fill: navy, font: { bold: true, color: white, size: 18 }, verticalAlignment: "center" };
  cell.format.rowHeight = 32;
  if (subtitle) {
    const row = Number(range.match(/\d+/)[0]) + 1;
    const start = range.match(/[A-Z]+/)[0];
    const end = range.split(":")[1].match(/[A-Z]+/)[0];
    sheet.getRange(`${start}${row}:${end}${row}`).merge();
    const sub = sheet.getRange(`${start}${row}`);
    sub.values = [[subtitle]];
    sub.format = { fill: "#E9EFF8", font: { color: muted, italic: true }, verticalAlignment: "center", wrapText: true };
    sub.format.rowHeight = 26;
  }
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => { sheet.getRange(`${excelColumn(index)}:${excelColumn(index)}`).format.columnWidth = width; });
}

function addPositionFormatting(range) {
  for (const [position, color] of Object.entries(positionColors)) {
    range.conditionalFormats.add("containsText", { text: position, format: { fill: color, font: { bold: true, color: ink } } });
  }
}

function addSignalFormatting(range) {
  const colors = { Target: "#B7E4C7", Value: green, Fair: blue, "Slight reach": "#FFE8CC", Pricey: "#FFD6D1", Depth: "#ECEEF2" };
  for (const [label, color] of Object.entries(colors)) {
    range.conditionalFormats.add("containsText", { text: label, format: { fill: color, font: { bold: true, color: ink } } });
  }
}

function addConfidenceFormatting(range) {
  for (const [label, color] of Object.entries({ High: green, Medium: gold, Low: red })) {
    range.conditionalFormats.add("containsText", { text: label, format: { fill: color, font: { bold: true, color: ink } } });
  }
}

function finishTable(sheet, tableRange, tableName, headerRow, lastRow) {
  const table = sheet.tables.add(tableRange, true, tableName);
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
  sheet.freezePanes.freezeRows(headerRow);
  sheet.showGridLines = false;
  sheet.getRange(tableRange).format.font = { name: "Arial", size: 10, color: ink };
  const lastCol = tableRange.split(":")[1].match(/[A-Z]+/)[0];
  sheet.getRange(`A${headerRow}:${lastCol}${headerRow}`).format.rowHeight = 25;
  sheet.getRange(`A${headerRow + 1}:${lastCol}${lastRow}`).format.rowHeight = 19;
  return table;
}

function formulaColumn(sheet, column, firstRow, lastRow, formula) {
  sheet.getRange(`${column}${firstRow}`).formulas = [[formula(firstRow)]];
  sheet.getRange(`${column}${firstRow}:${column}${lastRow}`).fillDown();
}

// Market-order board for live draft use.
{
  const sheet = wb.worksheets.add("Draft Board");
  styleTitle(sheet, "A1:X1", "2026 FANTASY DRAFT BOARD", "12-team PPR | independent forecast + confidence blend | positive gaps mean our model likes the player earlier than Sleeper");
  sheet.getRange("A3:X3").merge();
  sheet.getRange("A3").values = [["Use Status during the draft. Our 17G is the independent full-season pace; Decision blends it with Sleeper by confidence. Expected games affects only points above replacement."]];
  sheet.getRange("A3").format = { fill: gold, font: { color: ink }, wrapText: true };
  const headers = ["Status", "ADP", "Round", "Decision", "Draft Gap", "Independent", "Ind Gap", "Signal", "Player", "Pos", "Pos Rank", "Team", "Bye", "Our 17G", "Sleeper", "Proj Gap", "Decision Pts", "Exp G", "VBD", "Confidence", "Pass Rank", "Rush Rank", "Injury", "Why"];
  const startRow = 5;
  const rows = data.players_by_adp.map((p) => [
    "Available", rounded(p.adp), null, p.model_rank, null, p.independent_rank, null, p.signal, p.player, p.position,
    p.position_rank, p.team, p.bye, rounded(p.independent_points), rounded(p.sleeper_projected_points), null,
    rounded(p.projected_points), rounded(p.projected_games), rounded(p.vbd), p.confidence, p.team_pass_rank, p.team_rush_rank,
    p.injury || null, p.reason,
  ]);
  sheet.getRange(`A${startRow}:X${startRow + rows.length}`).values = [headers, ...rows];
  const first = startRow + 1;
  const last = startRow + rows.length;
  formulaColumn(sheet, "C", first, last, (r) => `=ROUNDUP(B${r}/12,0)`);
  formulaColumn(sheet, "E", first, last, (r) => `=B${r}-D${r}`);
  formulaColumn(sheet, "G", first, last, (r) => `=B${r}-F${r}`);
  formulaColumn(sheet, "P", first, last, (r) => `=N${r}-O${r}`);
  finishTable(sheet, `A${startRow}:X${last}`, "DraftBoardTable", startRow, last);
  sheet.freezePanes.freezeColumns(1);
  sheet.getRange(`A${first}:A${last}`).dataValidation = { rule: { type: "list", values: ["Available", "Taken", "Mine"] } };
  sheet.getRange(`A${first}:X${last}`).conditionalFormats.addCustom(`=$A${first}="Taken"`, { fill: "#E5E7EB", font: { color: "#8A9099", italic: true } });
  sheet.getRange(`A${first}:X${last}`).conditionalFormats.addCustom(`=$A${first}="Mine"`, { fill: green, font: { color: "#14532D", bold: true } });
  sheet.getRange(`E${first}:G${last}`).conditionalFormats.add("colorScale", { colors: ["#E67C73", gold, "#63BE7B"], thresholds: ["min", "50%", "max"] });
  sheet.getRange(`P${first}:P${last}`).conditionalFormats.add("colorScale", { colors: ["#E67C73", gold, "#63BE7B"], thresholds: ["min", "50%", "max"] });
  sheet.getRange(`S${first}:S${last}`).conditionalFormats.add("dataBar", { color: "#4B7BEC", gradient: true });
  addSignalFormatting(sheet.getRange(`H${first}:H${last}`));
  addPositionFormatting(sheet.getRange(`J${first}:J${last}`));
  addConfidenceFormatting(sheet.getRange(`T${first}:T${last}`));
  sheet.getRange(`W${first}:W${last}`).conditionalFormats.add("notContainsBlanks", { format: { fill: red, font: { bold: true, color: "#8B1E1E" } } });
  sheet.getRange(`B${first}:G${last}`).format.numberFormat = "0.0";
  sheet.getRange(`D${first}:D${last}`).format.numberFormat = "0";
  sheet.getRange(`F${first}:F${last}`).format.numberFormat = "0";
  sheet.getRange(`K${first}:M${last}`).format.numberFormat = "0";
  sheet.getRange(`N${first}:S${last}`).format.numberFormat = "0.0";
  sheet.getRange(`U${first}:V${last}`).format.numberFormat = "0";
  setWidths(sheet, [13,8,8,9,10,11,9,13,24,7,9,8,7,10,10,10,11,8,9,11,10,10,10,52]);
}

function addRankingSheet(name, players, independent) {
  const sheet = wb.worksheets.add(name);
  styleTitle(sheet, "A1:R1", independent ? "INDEPENDENT MODEL RANKINGS" : "DECISION RANKINGS", independent
    ? "No Sleeper projection or ADP is used in this forecast; low-confidence rookies remain deliberately visible"
    : "Independent forecast blended with Sleeper according to evidence confidence, then valued for this league");
  const headers = ["Rank", "ADP", "Gap", "Player", "Pos", "Team", "Bye", "Our 17G", "Sleeper", "Proj Gap", "Decision Pts", "Exp G", "VBD", "Confidence", "Pass Rank", "Rush Rank", "Injury", "Why"];
  const startRow = 4;
  const rows = players.map((p) => [
    independent ? p.independent_rank : p.model_rank, rounded(p.adp), null, p.player, p.position, p.team, p.bye,
    rounded(p.independent_points), rounded(p.sleeper_projected_points), rounded(p.projection_gap), rounded(p.projected_points),
    rounded(p.projected_games), rounded(independent ? p.independent_vbd : p.vbd), p.confidence, p.team_pass_rank, p.team_rush_rank,
    p.injury || null, p.reason,
  ]);
  sheet.getRange(`A${startRow}:R${startRow + rows.length}`).values = [headers, ...rows];
  const first = startRow + 1;
  const last = startRow + rows.length;
  formulaColumn(sheet, "C", first, last, (r) => `=B${r}-A${r}`);
  finishTable(sheet, `A${startRow}:R${last}`, independent ? "IndependentRankingsTable" : "DecisionRankingsTable", startRow, last);
  sheet.freezePanes.freezeColumns(1);
  sheet.getRange(`C${first}:C${last}`).conditionalFormats.add("colorScale", { colors: ["#E67C73", gold, "#63BE7B"], thresholds: ["min", "50%", "max"] });
  sheet.getRange(`J${first}:J${last}`).conditionalFormats.add("colorScale", { colors: ["#E67C73", gold, "#63BE7B"], thresholds: ["min", "50%", "max"] });
  sheet.getRange(`M${first}:M${last}`).conditionalFormats.add("dataBar", { color: "#4B7BEC", gradient: true });
  addPositionFormatting(sheet.getRange(`E${first}:E${last}`));
  addConfidenceFormatting(sheet.getRange(`N${first}:N${last}`));
  sheet.getRange(`Q${first}:Q${last}`).conditionalFormats.add("notContainsBlanks", { format: { fill: red, font: { bold: true, color: "#8B1E1E" } } });
  sheet.getRange(`A${first}:A${last}`).format.numberFormat = "0";
  sheet.getRange(`B${first}:C${last}`).format.numberFormat = "0.0";
  sheet.getRange(`G${first}:G${last}`).format.numberFormat = "0";
  sheet.getRange(`H${first}:M${last}`).format.numberFormat = "0.0";
  sheet.getRange(`O${first}:P${last}`).format.numberFormat = "0";
  setWidths(sheet, [8,8,9,24,7,8,7,10,10,10,11,8,9,11,10,10,10,52]);
}

addRankingSheet("Independent Model", data.players_by_independent, true);
addRankingSheet("Decision Rankings", data.players_by_model, false);

function addPositionSheet(position) {
  const sheet = wb.worksheets.add(position);
  const players = data.players_by_model.filter((p) => p.position === position).sort((a, b) => a.position_rank - b.position_rank);
  styleTitle(sheet, "A1:Z1", `${position} POSITION BOARD`, `Own projection, Sleeper comparison, team environment and expected opportunity | decision replacement: ${data.replacement_ranks[position]}`);
  const opportunityHeaders = position === "QB"
    ? ["Own Pass Att", "Sleeper Pass Att", "Own Carries", "Sleeper Carries"]
    : ["Own Targets", "Sleeper Targets", "Own Carries", "Sleeper Carries"];
  const headers = ["Pos Rank", "Decision", "Independent", "ADP", "Draft Gap", "Ind Gap", "Player", "Team", "Bye", "Our 17G", "Sleeper", "Proj Gap", "Decision Pts", "Exp G", "VBD", "Confidence", "Pass Rank", "Rush Rank", ...opportunityHeaders, "2025 PPG", "2025 G", "Injury", "Why"];
  const startRow = 4;
  const rows = players.map((p) => [
    p.position_rank, p.model_rank, p.independent_rank, rounded(p.adp), rounded(p.market_gap), rounded(p.independent_market_gap), p.player,
    p.team, p.bye, rounded(p.independent_points), rounded(p.sleeper_projected_points), rounded(p.projection_gap), rounded(p.projected_points),
    rounded(p.projected_games), rounded(p.vbd), p.confidence, p.team_pass_rank, p.team_rush_rank,
    position === "QB" ? rounded(p.own_pass_attempts) : rounded(p.own_targets),
    position === "QB" ? rounded(p.sleeper_pass_attempts) : rounded(p.sleeper_targets),
    rounded(p.own_carries), rounded(p.sleeper_carries), rounded(p.ppg_2025), p.games_2025 ?? null, p.injury || null, p.reason,
  ]);
  const lastCol = excelColumn(headers.length - 1);
  sheet.getRange(`A${startRow}:${lastCol}${startRow + rows.length}`).values = [headers, ...rows];
  const first = startRow + 1;
  const last = startRow + rows.length;
  finishTable(sheet, `A${startRow}:${lastCol}${last}`, `${position}PositionTable`, startRow, last);
  sheet.freezePanes.freezeColumns(1);
  sheet.getRange(`E${first}:F${last}`).conditionalFormats.add("colorScale", { colors: ["#E67C73", gold, "#63BE7B"], thresholds: ["min", "50%", "max"] });
  sheet.getRange(`J${first}:O${last}`).conditionalFormats.add("colorScale", { colors: ["#E67C73", gold, "#63BE7B"], thresholds: ["min", "50%", "max"] });
  addConfidenceFormatting(sheet.getRange(`P${first}:P${last}`));
  sheet.getRange(`Y${first}:Y${last}`).conditionalFormats.add("notContainsBlanks", { format: { fill: red, font: { bold: true, color: "#8B1E1E" } } });
  sheet.getRange(`A${first}:C${last}`).format.numberFormat = "0";
  sheet.getRange(`D${first}:F${last}`).format.numberFormat = "0.0";
  sheet.getRange(`I${first}:I${last}`).format.numberFormat = "0";
  sheet.getRange(`J${first}:O${last}`).format.numberFormat = "0.0";
  sheet.getRange(`Q${first}:R${last}`).format.numberFormat = "0";
  sheet.getRange(`S${first}:W${last}`).format.numberFormat = "0.0";
  sheet.getRange(`X${first}:X${last}`).format.numberFormat = "0";
  setWidths(sheet, [9,9,11,8,10,9,24,8,7,10,10,10,11,8,9,11,10,10,12,14,12,14,10,9,10,52]);
}

for (const position of ["QB", "RB", "WR", "TE"]) addPositionSheet(position);

// Forecast team pass/run environment.
{
  const sheet = wb.worksheets.add("Team Environment");
  styleTitle(sheet, "A1:L1", "2026 TEAM ENVIRONMENT", "Three-year weighted 2025-back forecast, shrunk 20% toward league average; rank 1 means highest projected volume");
  const headers = ["Pass Rank", "Team", "Pass Att/G", "Pass Rate", "Pass Yds/G", "Pass TD/G", "Rush Rank", "Carries/G", "Rush Yds/G", "Rush TD/G", "Plays/G", "Pass EPA/Att"];
  const rows = [...data.team_forecast].sort((a, b) => a.team_pass_rank - b.team_pass_rank).map((t) => [
    t.team_pass_rank, t.team, rounded(t.next_team_pass_attempts_pg, 2), rounded(t.next_team_pass_rate, 3), rounded(t.next_team_pass_yards_pg, 1), rounded(t.next_team_pass_tds_pg, 2),
    t.team_rush_rank, rounded(t.next_team_carries_pg, 2), rounded(t.next_team_rush_yards_pg, 1), rounded(t.next_team_rush_tds_pg, 2), rounded(t.next_team_plays_pg, 1), rounded(t.next_team_pass_epa_per_attempt, 3),
  ]);
  const startRow = 4;
  sheet.getRange(`A${startRow}:L${startRow + rows.length}`).values = [headers, ...rows];
  const first = startRow + 1;
  const last = startRow + rows.length;
  finishTable(sheet, `A${startRow}:L${last}`, "TeamEnvironmentTable", startRow, last);
  sheet.getRange(`C${first}:F${last}`).conditionalFormats.add("colorScale", { colors: ["#E67C73", gold, "#63BE7B"], thresholds: ["min", "50%", "max"] });
  sheet.getRange(`H${first}:K${last}`).conditionalFormats.add("colorScale", { colors: ["#E67C73", gold, "#63BE7B"], thresholds: ["min", "50%", "max"] });
  sheet.getRange(`A${first}:A${last}`).format.numberFormat = "0";
  sheet.getRange(`G${first}:G${last}`).format.numberFormat = "0";
  sheet.getRange(`C${first}:L${last}`).format.numberFormat = "0.00";
  sheet.getRange(`D${first}:D${last}`).format.numberFormat = "0.0%";
  setWidths(sheet, [10,9,12,11,12,11,10,12,12,11,10,13]);
}

// Walk-forward accuracy evidence.
{
  const sheet = wb.worksheets.add("Backtest");
  styleTitle(sheet, "A1:G1", "WALK-FORWARD BACKTEST", "2021–2025 seasons predicted only from earlier data | lower MAE is better; higher rank correlation is better");
  const selected = { QB: "team_model_ppg", RB: "player_only_ppg", WR: "team_model_ppg", TE: "team_model_ppg" };
  const rows = ["QB", "RB", "WR", "TE"].map((position) => {
    const model = data.backtest_overall.find((r) => r.position === position && r.model === selected[position]);
    const baseline = data.backtest_overall.find((r) => r.position === position && r.model === "prior_year_ppg");
    return [position, selected[position] === "team_model_ppg" ? "Team-aware ridge" : "Player-only ridge", rounded(model.mae, 3), rounded(baseline.mae, 3), null, rounded(model.rank_correlation, 3), model.players];
  });
  sheet.getRange("A4:G8").values = [["Pos", "Selected Model", "Model MAE", "Repeat Prior-Year MAE", "MAE Improvement", "Rank Corr", "Player Tests"], ...rows];
  formulaColumn(sheet, "E", 5, 8, (r) => `=D${r}-C${r}`);
  finishTable(sheet, "A4:G8", "BacktestSelectedTable", 4, 8);
  sheet.getRange("E5:E8").conditionalFormats.add("colorScale", { colors: ["#E67C73", gold, "#63BE7B"], thresholds: ["min", "50%", "max"] });
  sheet.getRange("C5:F8").format.numberFormat = "0.000";
  sheet.getRange("G5:G8").format.numberFormat = "0";
  setWidths(sheet, [8,20,12,21,16,12,13]);
  const chart = sheet.charts.add("bar", {
    chartType: "bar",
    title: "Next-season PPR PPG error: model vs repeat last year",
    hasLegend: true,
  });
  const modelSeries = chart.series.add("Model MAE");
  modelSeries.categoryFormula = "'Backtest'!$A$5:$A$8";
  modelSeries.formula = "'Backtest'!$C$5:$C$8";
  modelSeries.fill = "#F2762E";
  const baselineSeries = chart.series.add("Repeat Prior-Year MAE");
  baselineSeries.categoryFormula = "'Backtest'!$A$5:$A$8";
  baselineSeries.formula = "'Backtest'!$D$5:$D$8";
  baselineSeries.fill = "#1B6F2A";
  chart.title = "Next-season PPR PPG error: model vs repeat last year";
  chart.hasLegend = true;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 10 } };
  chart.yAxis = { numberFormatCode: "0.0" };
  chart.setPosition("A11", "G27");
}

// Printable market-order board inspired by the user's reference PDF.
{
  const sheet = wb.worksheets.add("Print Board");
  sheet.showGridLines = false;
  const players = data.players_by_adp.slice(0, 240);
  const perPage = 80;
  const perPanel = 40;
  const headers = ["ADP", "Player", "ADP Pos", "Team", "Dec", "Ind", "Gap", "Pick"];
  for (let page = 0; page < 3; page++) {
    const titleRow = 1 + page * 44;
    const headerRow = titleRow + 1;
    const dataRow = headerRow + 1;
    sheet.getRange(`A${titleRow}:Q${titleRow}`).merge();
    sheet.getRange(`A${titleRow}`).values = [[`2026 DRAFT BOARD - PPR - PAGE ${page + 1}`]];
    sheet.getRange(`A${titleRow}`).format = { fill: navy, font: { bold: true, color: white, size: 15 }, horizontalAlignment: "center" };
    for (let panel = 0; panel < 2; panel++) {
      const startCol = panel === 0 ? 0 : 9;
      const panelPlayers = players.slice(page * perPage + panel * perPanel, page * perPage + (panel + 1) * perPanel);
      const lastCol = excelColumn(startCol + headers.length - 1);
      const firstCol = excelColumn(startCol);
      sheet.getRange(`${firstCol}${headerRow}:${lastCol}${headerRow}`).values = [headers];
      sheet.getRange(`${firstCol}${headerRow}:${lastCol}${headerRow}`).format = { fill: "#31476D", font: { bold: true, color: white }, horizontalAlignment: "center" };
      const rows = panelPlayers.map((p) => [rounded(p.adp), p.player, p.adp_position_label, p.team, p.model_rank, p.independent_rank, rounded(p.market_gap), null]);
      if (rows.length) {
        sheet.getRange(`${firstCol}${dataRow}:${lastCol}${dataRow + rows.length - 1}`).values = rows;
        sheet.getRange(`${firstCol}${dataRow}:${lastCol}${dataRow + rows.length - 1}`).format = { font: { name: "Arial", size: 9, color: ink }, rowHeight: 18, borders: { preset: "inside", style: "thin", color: "#E4E7EC" } };
        addPositionFormatting(sheet.getRange(`${excelColumn(startCol + 2)}${dataRow}:${excelColumn(startCol + 2)}${dataRow + rows.length - 1}`));
        sheet.getRange(`${excelColumn(startCol + 6)}${dataRow}:${excelColumn(startCol + 6)}${dataRow + rows.length - 1}`).conditionalFormats.add("colorScale", { colors: ["#E67C73", gold, "#63BE7B"], thresholds: ["min", "50%", "max"] });
        sheet.getRange(`${firstCol}${dataRow}:${firstCol}${dataRow + rows.length - 1}`).format.numberFormat = "0.0";
      }
    }
  }
  setWidths(sheet, [7,21,8,7,6,6,7,7,2,7,21,8,7,6,6,7,7]);
  sheet.freezePanes.freezeRows(2);
}

// Kicker and defense market list.
{
  const sheet = wb.worksheets.add("K & DEF");
  styleTitle(sheet, "A1:H1", "KICKER & DEFENSE", "Retained in market order; intentionally excluded from the skill-position forecast and VBD model");
  const headers = ["ADP", "Round", "Player", "Pos", "Team", "Bye", "Sleeper Pts", "Injury"];
  const rows = data.kicker_defense.map((p) => [rounded(p.adp), Math.ceil(p.adp / 12), p.player, p.position, p.team, p.bye, rounded(p.sleeper_projected_points ?? p.projected_points), p.injury || null]);
  sheet.getRange(`A4:H${4 + rows.length}`).values = [headers, ...rows];
  finishTable(sheet, `A4:H${4 + rows.length}`, "KickerDefenseTable", 4, 4 + rows.length);
  addPositionFormatting(sheet.getRange(`D5:D${4 + rows.length}`));
  sheet.getRange(`A5:A${4 + rows.length}`).format.numberFormat = "0.0";
  sheet.getRange(`B5:B${4 + rows.length}`).format.numberFormat = "0";
  sheet.getRange(`F5:F${4 + rows.length}`).format.numberFormat = "0";
  sheet.getRange(`G5:G${4 + rows.length}`).format.numberFormat = "0.0";
  setWidths(sheet, [9,8,25,7,8,7,12,12]);
}

// Plain-language audit trail and source URLs.
{
  const sheet = wb.worksheets.add("Method & Sources");
  styleTitle(sheet, "A1:H1", "METHOD, ASSUMPTIONS & SOURCES", "The workbook is designed to make the independent forecast, confidence blend and league valuation auditable");
  sheet.showGridLines = false;
  const methodRows = [
    ["Independent forecast", "Position-specific ridge regression trained on 2015–2025 NFL regular seasons. A row from season A predicts season A+1; Sleeper projection and ADP are excluded."],
    ["Team environment", "Destination team's prior three seasons: 55% most recent, 30% prior, 15% third; then 20% shrinkage toward that season's league average."],
    ["RB exception", "Team-aware RB PPG was tested but player-only Ridge had slightly lower walk-forward MAE (2.800 vs 2.818). Team context remains in RB opportunity explanations."],
    ["Expected games", "Games-played Ridge forecast shrunk 25% toward a 14-game active-player prior. Missing weeks reduce only points above replacement because a substitute can play."],
    ["Decision blend", "High confidence: 65% independent / 35% Sleeper. Medium: 50% / 50%. Low: 25% / 75%. Unmodeled: Sleeper only."],
    ["Independent VBD", "(Independent PPG - independent replacement PPG) × expected games."],
    ["Decision VBD", "(Decision PPG - decision replacement PPG) × expected games."],
    ["Draft Gap", "Sleeper ADP minus Decision Rank. Positive means the model values the player earlier than the market price."],
    ["Projection Gap", "Independent 17-game points minus Sleeper projected points. Positive means our football forecast is higher."],
    ["Rookies", "Draft pick, age and destination-team environment. No college production is included, so confidence is Low and the decision blend leans 75% on Sleeper."],
    ["Sleeper targets", "The live Sleeper table supplied dashes rather than target projections. Own target forecasts remain available; blank Sleeper target cells mean unavailable, not zero."],
  ];
  sheet.getRange("A4:B14").values = methodRows;
  sheet.getRange("A4:A14").format = { fill: "#E9EFF8", font: { bold: true, color: ink }, verticalAlignment: "top" };
  sheet.getRange("B4:B14").format = { fill: white, font: { color: ink }, wrapText: true, verticalAlignment: "top" };
  sheet.getRange("A4:B14").format.borders = { preset: "inside", style: "thin", color: line };
  sheet.getRange("A4:B14").format.rowHeight = 42;
  sheet.getRange("A16:B16").merge();
  sheet.getRange("A16").values = [["SOURCE URLS"]];
  sheet.getRange("A16").format = { fill: navy, font: { bold: true, color: white } };
  const sources = [
    ["NFLverse player summaries", "https://github.com/nflverse/nflverse-data/releases/tag/stats_player"],
    ["NFLverse team summaries", "https://github.com/nflverse/nflverse-data/releases/tag/stats_team"],
    ["NFLverse player registry", "https://github.com/nflverse/nflverse-data/releases/tag/players"],
    ["NFLverse draft picks", "https://github.com/nflverse/nflverse-data/releases/tag/draft_picks"],
    ["Sleeper fantasy football", "https://sleeper.com/fantasy-football"],
    ["FantasyPros 2025 PPR context", "https://www.fantasypros.com/nfl/stats/qb.php"],
  ];
  sheet.getRange("A17:B22").values = sources;
  sheet.getRange("A17:A22").format = { fill: light, font: { bold: true, color: ink } };
  sheet.getRange("B17:B22").format = { font: { color: "#1D4ED8", underline: true }, wrapText: true };
  sheet.getRange("A24:B27").values = [
    ["League", "12 teams, PPR, 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, K, DEF, 7 bench"],
    ["Replacement ranks", `QB ${data.replacement_ranks.QB}; RB ${data.replacement_ranks.RB}; WR ${data.replacement_ranks.WR}; TE ${data.replacement_ranks.TE}`],
    ["FLEX allocation", `${data.flex_allocation.RB} RB; ${data.flex_allocation.WR} WR; ${data.flex_allocation.TE} TE from the decision forecast`],
    ["Generated", `UTC ${data.generated_at}`],
  ];
  sheet.getRange("A24:A27").format = { fill: "#E9EFF8", font: { bold: true, color: ink } };
  sheet.getRange("B24:B27").format = { wrapText: true, font: { color: ink } };
  setWidths(sheet, [25,95]);
}

// Compact verification before export.
const boardCheck = await wb.inspect({ kind: "region", sheetId: "Draft Board", range: "A1:X15", maxChars: 5000 });
console.log(boardCheck.ndjson);
const errorCheck = await wb.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errorCheck.ndjson);

for (const name of ["Draft Board", "Independent Model", "Decision Rankings", "QB", "RB", "WR", "TE", "Team Environment", "Backtest", "Print Board", "K & DEF", "Method & Sources"]) {
  const preview = await wb.render({ sheetName: name, autoCrop: "all", scale: 1, format: "png" });
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  await fs.writeFile(path.join(previewDir, `${slug}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(path.join(outputDir, "2026-independent-fantasy-draft-board.xlsx"));
console.log(`Saved ${path.join(outputDir, "2026-independent-fantasy-draft-board.xlsx")}`);
