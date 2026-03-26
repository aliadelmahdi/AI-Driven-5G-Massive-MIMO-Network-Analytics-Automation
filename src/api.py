from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

from .analyze_data import analyze_datasets
from .db import bootstrap_database_from_csvs, database_snapshot
from .schemas import AnalyzeRequest, DatabaseLoadRequest, PipelineResponse
from .utils import OUTPUT_DIR, load_json

app = FastAPI(title="Telecom 5G Massive MIMO Analytics API", version="0.1.0")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


def _safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _load_enriched_index() -> dict[tuple[str, str, str], dict]:
    enriched_path = OUTPUT_DIR / "llm_enriched_incidents.json"
    if not enriched_path.exists():
        return {}

    try:
        incidents = load_json(enriched_path)
    except Exception:
        return {}

    index: dict[tuple[str, str, str], dict] = {}
    for item in incidents:
        key = (
            str(item.get("time_window", "")),
            str(item.get("cell_id", "")),
            str(item.get("beam_id", "")),
        )
        index[key] = item
    return index


def _format_diagnosis_label(value: str) -> str:
    return str(value or "issue").replace("_", " ")


def _build_simple_insight(row: dict, enriched: dict) -> str:
    diagnosis = _format_diagnosis_label(row.get("diagnosis", "issue"))
    signals: list[str] = []

    if float(row.get("avg_sinr_db", 0.0) or 0.0) < 0:
        signals.append("weak radio quality")
    if float(row.get("avg_bler_dl_pct", 0.0) or 0.0) >= 20:
        signals.append("high BLER")
    if float(row.get("prb_utilization_pct", 0.0) or 0.0) >= 85:
        signals.append("high load")
    if float(row.get("ue_avg_latency_ms", 0.0) or 0.0) >= 40:
        signals.append("high latency")
    if float(row.get("ue_avg_packet_loss_pct", 0.0) or 0.0) >= 2:
        signals.append("packet loss")

    headline = enriched.get("alert_summary") or row.get("short_summary") or ""
    if signals:
        return f"{diagnosis.capitalize()} driven by {', '.join(signals[:2])}."
    if headline:
        return str(headline).strip().rstrip(".") + "."
    return f"{diagnosis.capitalize()} detected on this beam."


def _select_balanced_incidents(incidents: pd.DataFrame, limit: int) -> pd.DataFrame:
    sorted_incidents = incidents.sort_values(
        ["severity_rank", "beam_health_score", "affected_ue_count"],
        ascending=[False, True, False],
    )
    if len(sorted_incidents) <= limit:
        return sorted_incidents

    severity_order = ["critical", "high", "medium", "low"]
    groups: list[list[int]] = []
    for severity in severity_order:
        severity_rows = sorted_incidents[sorted_incidents["severity"] == severity]
        if not severity_rows.empty:
            groups.append(severity_rows.index.tolist())

    if not groups:
        return sorted_incidents.head(limit)

    selected_indices: list[int] = []
    cursor = 0
    while len(selected_indices) < limit and groups:
        group = groups[cursor % len(groups)]
        if group:
            selected_indices.append(group.pop(0))
        else:
            groups.pop(cursor % len(groups))
            continue
        cursor += 1

    return sorted_incidents.loc[selected_indices]


def _build_dashboard_payload(limit: int = 200) -> dict:
    incidents = _safe_read_csv(OUTPUT_DIR / "incidents_summary.csv")
    if incidents.empty:
        return {
            "status": "empty",
            "message": "No incidents_summary.csv found yet. Run analysis first.",
            "summary": {},
            "incidents": [],
        }

    incidents = incidents.copy()
    incidents["beam_health_score"] = pd.to_numeric(incidents["beam_health_score"], errors="coerce")
    incidents["affected_ue_count"] = pd.to_numeric(incidents["affected_ue_count"], errors="coerce").fillna(0).astype(int)
    incidents["severity_rank"] = pd.to_numeric(incidents["severity_rank"], errors="coerce").fillna(0)

    enriched_index = _load_enriched_index()
    sorted_incidents = _select_balanced_incidents(incidents, limit)

    top_diagnosis = (
        incidents["diagnosis"].value_counts().head(5).rename_axis("label").reset_index(name="count").to_dict(orient="records")
    )
    top_severity = (
        incidents["severity"].value_counts().rename_axis("label").reset_index(name="count").to_dict(orient="records")
    )

    summary = {
        "total_incidents": int(len(incidents)),
        "critical_incidents": int((incidents["severity"] == "critical").sum()),
        "high_incidents": int((incidents["severity"] == "high").sum()),
        "average_health_score": round(float(incidents["beam_health_score"].mean()), 2),
        "lowest_health_score": round(float(incidents["beam_health_score"].min()), 2),
        "highest_affected_ues": int(incidents["affected_ue_count"].max()),
        "top_diagnosis": top_diagnosis,
        "severity_breakdown": top_severity,
    }

    dashboard_rows = []
    for row in sorted_incidents.to_dict(orient="records"):
        key = (str(row.get("time_window", "")), str(row.get("cell_id", "")), str(row.get("beam_id", "")))
        enriched = enriched_index.get(key, {})
        dashboard_rows.append(
            {
                "time_window": row.get("time_window", ""),
                "cell_id": row.get("cell_id", ""),
                "beam_id": row.get("beam_id", ""),
                "diagnosis": row.get("diagnosis", ""),
                "severity": row.get("severity", ""),
                "affected_ue_count": int(row.get("affected_ue_count", 0) or 0),
                "beam_health_score": round(float(row.get("beam_health_score", 0.0) or 0.0), 2),
                "short_summary": row.get("short_summary", ""),
                "recommended_action": row.get("recommended_action", ""),
                "avg_sinr_db": round(float(row.get("avg_sinr_db", 0.0) or 0.0), 2),
                "avg_rsrp_dbm": round(float(row.get("avg_rsrp_dbm", 0.0) or 0.0), 2),
                "avg_bler_dl_pct": round(float(row.get("avg_bler_dl_pct", 0.0) or 0.0), 2),
                "prb_utilization_pct": round(float(row.get("prb_utilization_pct", 0.0) or 0.0), 2),
                "ue_avg_latency_ms": round(float(row.get("ue_avg_latency_ms", 0.0) or 0.0), 2),
                "ue_avg_packet_loss_pct": round(float(row.get("ue_avg_packet_loss_pct", 0.0) or 0.0), 2),
                "congestion_score": round(float(row.get("congestion_score", 0.0) or 0.0), 2),
                "coverage_score": round(float(row.get("coverage_score", 0.0) or 0.0), 2),
                "interference_risk_score": round(float(row.get("interference_risk_score", 0.0) or 0.0), 2),
                "mobility_stress_score": round(float(row.get("mobility_stress_score", 0.0) or 0.0), 2),
                "reliability_score": round(float(row.get("reliability_score", 0.0) or 0.0), 2),
                "llm_explanation": enriched.get("explanation", ""),
                "llm_root_cause": enriched.get("root_cause", ""),
                "llm_recommendation": enriched.get("recommendation", ""),
                "llm_alert_summary": enriched.get("alert_summary", ""),
                "simple_insight": _build_simple_insight(row, enriched),
            }
        )

    return {"status": "ok", "message": "Dashboard data ready", "summary": summary, "incidents": dashboard_rows}


def export_static_dashboard(target_dir: Path, limit: int = 200) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = _build_dashboard_payload(limit=limit)

    (target_dir / "dashboard-data.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    static_html = DASHBOARD_HTML.replace("fetch('/api/dashboard-data')", "fetch('./dashboard-data.json')")
    static_html = static_html.replace(
        "</section>\n  </div>",
        """</section>
    <p class="muted" style="margin-top:16px;">This is a published snapshot from the repository output files. To refresh it, run <code>main.py export-dashboard</code> and push the updated <code>docs/</code> folder.</p>
  </div>""",
    )
    (target_dir / "index.html").write_text(static_html, encoding="utf-8")
    (target_dir / ".nojekyll").write_text("", encoding="utf-8")
    return target_dir


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Telecom Incident Dashboard</title>
  <style>
    :root {
      --bg: #f4f7fb;
      --card: #ffffff;
      --ink: #14233b;
      --muted: #5c6b80;
      --line: #d7e0ea;
      --accent: #0f766e;
      --danger: #b91c1c;
      --warn: #b45309;
      --good: #166534;
      --header: #123456;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background: linear-gradient(180deg, #eef4fb 0%, #f9fbfd 100%);
      color: var(--ink);
    }
    .shell {
      max-width: 1400px;
      margin: 0 auto;
      padding: 24px;
    }
    .hero {
      background: linear-gradient(135deg, #123456 0%, #0f766e 100%);
      color: white;
      border-radius: 20px;
      padding: 28px;
      margin-bottom: 20px;
      box-shadow: 0 18px 35px rgba(18, 52, 86, 0.18);
    }
    .hero h1 { margin: 0 0 8px; font-size: 32px; }
    .hero p { margin: 0; color: rgba(255,255,255,.86); }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 10px 24px rgba(20, 35, 59, 0.06);
    }
    .card h3 {
      margin: 0 0 8px;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: .08em;
      color: var(--muted);
    }
    .metric {
      font-size: 34px;
      font-weight: 700;
    }
    .layout {
      display: grid;
      grid-template-columns: 1.2fr .8fr;
      gap: 18px;
    }
    .table-note {
      margin-bottom: 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 14px;
    }
    input, select {
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: white;
      min-width: 180px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    th, td {
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: var(--muted);
    }
    tr:hover { background: #f7fafc; cursor: pointer; }
    .pill {
      display: inline-block;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 700;
    }
    .sev-critical { background: #fee2e2; color: var(--danger); }
    .sev-high { background: #ffedd5; color: var(--warn); }
    .sev-medium { background: #fef9c3; color: #854d0e; }
    .sev-low { background: #dcfce7; color: var(--good); }
    .bars { display: grid; gap: 10px; margin-top: 14px; }
    .bar-row { display: grid; gap: 6px; }
    .bar-track { background: #edf2f7; border-radius: 999px; overflow: hidden; height: 10px; }
    .bar-fill { background: linear-gradient(90deg, #123456, #0f766e); height: 100%; }
    .detail dl {
      margin: 0;
      display: grid;
      grid-template-columns: 160px 1fr;
      gap: 10px 12px;
    }
    .detail dt { color: var(--muted); font-weight: 600; }
    .detail dd { margin: 0; }
    .muted { color: var(--muted); }
    .empty {
      padding: 32px;
      text-align: center;
      color: var(--muted);
    }
    @media (max-width: 1100px) {
      .grid, .layout { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <h1>Telecom Incident Dashboard</h1>
      <p>Readable view of <code>incidents_summary.csv</code> with top risk patterns, severity mix, and per-incident insights.</p>
    </section>

    <section class="grid" id="summary-cards"></section>

    <section class="layout">
      <div class="card">
        <div class="toolbar">
          <input id="searchBox" type="search" placeholder="Search cell, beam, diagnosis..." />
          <select id="severityFilter">
            <option value="">All severities</option>
          </select>
          <select id="diagnosisFilter">
            <option value="">All diagnoses</option>
          </select>
        </div>
        <div style="overflow:auto; max-height: 680px;">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Cell/Beam</th>
                <th>Severity</th>
                <th>Diagnosis</th>
                <th>Insight</th>
                <th>Health</th>
                <th>Affected UEs</th>
              </tr>
            </thead>
            <tbody id="incidentRows"></tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h3>Incident Insight</h3>
        <div id="incidentDetail" class="detail empty">Select an incident to inspect its KPIs, root cause, and recommendation.</div>
        <div class="bars" id="summaryBars"></div>
      </div>
    </section>
  </div>

  <script>
    const state = { payload: null, filtered: [], selectedIndex: 0 };

    const severityClass = (value) => `pill sev-${String(value || '').toLowerCase()}`;

    async function loadDashboard() {
      const response = await fetch('/api/dashboard-data');
      const payload = await response.json();
      state.payload = payload;

      if (payload.status !== 'ok') {
        document.getElementById('summary-cards').innerHTML = `<div class="card">${payload.message}</div>`;
        document.getElementById('incidentRows').innerHTML = '';
        document.getElementById('incidentDetail').textContent = payload.message;
        return;
      }

      renderSummary(payload.summary);
      buildFilters(payload.incidents);
      applyFilters();
    }

    function renderSummary(summary) {
      const cards = [
        ['Total Incidents', summary.total_incidents],
        ['Critical Incidents', summary.critical_incidents],
        ['Average Health', summary.average_health_score],
        ['Highest Affected UEs', summary.highest_affected_ues],
      ];
      document.getElementById('summary-cards').innerHTML = cards.map(([label, value]) => `
        <div class="card">
          <h3>${label}</h3>
          <div class="metric">${value}</div>
        </div>
      `).join('');

      const severityBars = [];
      const severityMax = Math.max(...summary.severity_breakdown.map(item => item.count), 1);
      for (const item of summary.severity_breakdown) {
        severityBars.push(`
          <div class="bar-row">
            <div><strong>${item.label}</strong> <span class="muted">(${item.count})</span></div>
            <div class="bar-track"><div class="bar-fill" style="width:${(item.count / severityMax) * 100}%"></div></div>
          </div>
        `);
      }

      const diagnosisMax = Math.max(...summary.top_diagnosis.map(item => item.count), 1);
      const bars = [];
      for (const item of summary.top_diagnosis) {
        bars.push(`
          <div class="bar-row">
            <div><strong>${item.label}</strong> <span class="muted">(${item.count})</span></div>
            <div class="bar-track"><div class="bar-fill" style="width:${(item.count / diagnosisMax) * 100}%"></div></div>
          </div>
        `);
      }
      document.getElementById('summaryBars').innerHTML = `
        <h3>Severity Mix</h3>
        ${severityBars.join('')}
        <h3>Top Diagnosis Patterns</h3>
        ${bars.join('')}
      `;
    }

    function buildFilters(incidents) {
      const severitySelect = document.getElementById('severityFilter');
      const diagnosisSelect = document.getElementById('diagnosisFilter');

      const severities = [...new Set(incidents.map(item => item.severity))];
      const diagnoses = [...new Set(incidents.map(item => item.diagnosis))];

      severitySelect.innerHTML = '<option value="">All severities</option>' + severities.map(v => `<option value="${v}">${v}</option>`).join('');
      diagnosisSelect.innerHTML = '<option value="">All diagnoses</option>' + diagnoses.map(v => `<option value="${v}">${v}</option>`).join('');

      document.getElementById('searchBox').addEventListener('input', applyFilters);
      severitySelect.addEventListener('change', applyFilters);
      diagnosisSelect.addEventListener('change', applyFilters);
    }

    function applyFilters() {
      const search = document.getElementById('searchBox').value.toLowerCase().trim();
      const severity = document.getElementById('severityFilter').value;
      const diagnosis = document.getElementById('diagnosisFilter').value;

      state.filtered = state.payload.incidents.filter(item => {
        const haystack = `${item.time_window} ${item.cell_id} ${item.beam_id} ${item.diagnosis} ${item.short_summary} ${item.simple_insight}`.toLowerCase();
        return (!search || haystack.includes(search))
          && (!severity || item.severity === severity)
          && (!diagnosis || item.diagnosis === diagnosis);
      });

      state.selectedIndex = 0;
      renderTable();
      renderDetail();
    }

    function renderTable() {
      const tbody = document.getElementById('incidentRows');
      if (!state.filtered.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">No incidents match the current filter.</td></tr>';
        return;
      }

      tbody.innerHTML = state.filtered.map((item, index) => `
        <tr data-index="${index}">
          <td>${item.time_window}</td>
          <td><strong>${item.cell_id}</strong><br><span class="muted">${item.beam_id}</span></td>
          <td><span class="${severityClass(item.severity)}">${item.severity}</span></td>
          <td>${item.diagnosis}</td>
          <td>${item.simple_insight}</td>
          <td>${item.beam_health_score}</td>
          <td>${item.affected_ue_count}</td>
        </tr>
      `).join('');

      tbody.querySelectorAll('tr[data-index]').forEach(row => {
        row.addEventListener('click', () => {
          state.selectedIndex = Number(row.dataset.index);
          renderDetail();
        });
      });
    }

    function renderDetail() {
      const detail = document.getElementById('incidentDetail');
      const item = state.filtered[state.selectedIndex];
      if (!item) {
        detail.textContent = 'No incident selected.';
        return;
      }

      const recommendation = item.llm_recommendation || item.recommended_action;
      const explanation = item.simple_insight;
      const rootCause = item.llm_root_cause || item.diagnosis;

      detail.classList.remove('empty');
      detail.innerHTML = `
        <dl>
          <dt>Time Window</dt><dd>${item.time_window}</dd>
          <dt>Cell / Beam</dt><dd>${item.cell_id} / ${item.beam_id}</dd>
          <dt>Severity</dt><dd><span class="${severityClass(item.severity)}">${item.severity}</span></dd>
          <dt>Diagnosis</dt><dd>${item.diagnosis}</dd>
          <dt>Health Score</dt><dd>${item.beam_health_score}</dd>
          <dt>Affected UEs</dt><dd>${item.affected_ue_count}</dd>
          <dt>Simple Insight</dt><dd>${explanation}</dd>
          <dt>Summary</dt><dd>${item.short_summary}</dd>
          <dt>Likely Root Cause</dt><dd>${rootCause}</dd>
          <dt>Recommendation</dt><dd>${recommendation}</dd>
          <dt>SINR / RSRP</dt><dd>${item.avg_sinr_db} dB / ${item.avg_rsrp_dbm} dBm</dd>
          <dt>BLER / PRB</dt><dd>${item.avg_bler_dl_pct}% / ${item.prb_utilization_pct}%</dd>
          <dt>Latency / Loss</dt><dd>${item.ue_avg_latency_ms} ms / ${item.ue_avg_packet_loss_pct}%</dd>
          <dt>Problem Scores</dt><dd>
            Congestion ${item.congestion_score},
            Coverage ${item.coverage_score},
            Interference ${item.interference_risk_score},
            Mobility ${item.mobility_stress_score},
            Reliability ${item.reliability_score}
          </dd>
        </dl>
      `;
    }

    loadDashboard();
  </script>
</body>
</html>
""".strip()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "telecom-analytics", "output_dir": str(OUTPUT_DIR)}


@app.post("/bootstrap-db")
def bootstrap_db(request: DatabaseLoadRequest) -> dict:
    counts = bootstrap_database_from_csvs(force_reload=request.force_reload)
    return {"status": "ok", "message": "MySQL loaded from existing CSV files", **counts}


@app.get("/data-source-status")
def data_source_status() -> dict:
    return database_snapshot()


@app.post("/analyze", response_model=PipelineResponse)
def analyze(request: AnalyzeRequest) -> PipelineResponse:
    artifacts = analyze_datasets(enrich_with_llm=False, top_n_incidents=request.top_n_incidents, force_reload_db=request.force_reload)
    return PipelineResponse(
        status="ok",
        message="Analysis complete",
        ue_rows=artifacts.ue_rows,
        beam_rows=artifacts.beam_rows,
        incidents=len(artifacts.incidents),
        output_dir=str(OUTPUT_DIR),
        llm_used=False,
        report_path=str(OUTPUT_DIR / "top_incidents_report.md"),
    )


@app.post("/analyze-and-enrich", response_model=PipelineResponse)
def analyze_and_enrich(request: AnalyzeRequest) -> PipelineResponse:
    artifacts = analyze_datasets(enrich_with_llm=True, top_n_incidents=request.top_n_incidents, force_reload_db=request.force_reload)
    return PipelineResponse(
        status="ok",
        message="Analysis and enrichment complete",
        ue_rows=artifacts.ue_rows,
        beam_rows=artifacts.beam_rows,
        incidents=len(artifacts.incidents),
        output_dir=str(OUTPUT_DIR),
        llm_used=artifacts.llm_used,
        report_path=str(OUTPUT_DIR / "top_incidents_report.md"),
    )


@app.get("/top-incidents")
def top_incidents(limit: int = 10) -> dict:
    incidents = load_json(OUTPUT_DIR / "llm_enriched_incidents.json")
    return {"status": "ok", "count": min(limit, len(incidents)), "incidents": incidents[:limit]}


@app.get("/api/dashboard-data")
def dashboard_data_api(limit: int = 200) -> dict:
    return _build_dashboard_payload(limit=limit)


@app.get("/dashboard-data", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
def dashboard_home() -> str:
    return DASHBOARD_HTML
