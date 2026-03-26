from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable

import pandas as pd

from .anomalies import detect_anomalies
from .db import bootstrap_database_from_csvs, load_measurements_from_mysql
from .features import engineer_features
from .ollama_client import enrich_incident_with_ollama
from .report_builder import build_markdown_report
from .rules import classify_incidents
from .utils import OUTPUT_DIR, ensure_directories, save_json


@dataclass
class AnalysisArtifacts:
    ue_rows: int
    beam_rows: int
    joined: pd.DataFrame
    incidents: pd.DataFrame
    llm_payload: list[dict]
    enriched_payload: list[dict]
    report_markdown: str
    llm_used: bool


ProgressCallback = Callable[[str, str], None]


def _aggregate_ue(ue_df: pd.DataFrame) -> pd.DataFrame:
    ue_df = ue_df.copy()
    ue_df["timestamp_utc"] = pd.to_datetime(ue_df["timestamp_utc"], utc=True)
    ue_df["window_start_utc"] = ue_df["timestamp_utc"].dt.floor("5min")
    ue_df["handover_flag"] = ue_df["handover_event"].eq("yes").astype(int)
    ue_df["low_quality_flag"] = ((ue_df["sinr_db"] < 5) | (ue_df["rsrp_dbm"] < -100)).astype(int)
    ue_df["high_bler_flag"] = (ue_df["bler_dl_pct"] >= 12).astype(int)
    ue_df["high_latency_flag"] = (ue_df["latency_ms"] >= 50).astype(int)
    aggregated = (
        ue_df.groupby(["window_start_utc", "serving_cell_id", "beam_id"], as_index=False)
        .agg(
            ue_row_count=("ue_id", "size"),
            distinct_ue_count=("ue_id", "nunique"),
            ue_avg_sinr_db=("sinr_db", "mean"),
            ue_avg_bler_dl_pct=("bler_dl_pct", "mean"),
            ue_avg_dl_throughput_mbps=("dl_throughput_mbps", "mean"),
            ue_avg_ul_throughput_mbps=("ul_throughput_mbps", "mean"),
            ue_avg_latency_ms=("latency_ms", "mean"),
            ue_avg_packet_loss_pct=("packet_loss_pct", "mean"),
            ue_avg_velocity_kph=("velocity_kph", "mean"),
            ue_avg_jitter_ms=("jitter_ms", "mean"),
            ue_avg_harq_retx_pct=("harq_retx_pct", "mean"),
            ue_avg_traffic_load_mb=("traffic_load_mb", "mean"),
            ue_handover_ratio=("handover_flag", "mean"),
            ue_low_quality_count=("low_quality_flag", "sum"),
            ue_high_bler_count=("high_bler_flag", "sum"),
            ue_high_latency_count=("high_latency_flag", "sum"),
        )
        .rename(columns={"serving_cell_id": "cell_id"})
    )
    aggregated["window_start_utc"] = aggregated["window_start_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return aggregated


def _severity_rank(series: pd.Series) -> pd.Series:
    return series.map({"low": 1, "medium": 2, "high": 3, "critical": 4}).fillna(0).astype(int)


def _emit_progress(progress: ProgressCallback | None, message: str, eta: str) -> None:
    if progress is not None:
        progress(message, eta)


def analyze_datasets(
    enrich_with_llm: bool = False,
    top_n_incidents: int = 25,
    force_reload_db: bool = False,
    progress: ProgressCallback | None = None,
) -> AnalysisArtifacts:
    ensure_directories()
    started_at = perf_counter()
    _emit_progress(progress, "Preparing MySQL-backed datasets", "ETA 8-30s")
    bootstrap_database_from_csvs(force_reload=force_reload_db, progress=progress)
    ue_df, beam_df = load_measurements_from_mysql(progress=progress)
    _emit_progress(progress, f"Loaded data: UE rows={len(ue_df):,}, beam rows={len(beam_df):,}", "ETA 5-10s")
    beam_df = beam_df.copy()
    beam_df["window_start_utc"] = pd.to_datetime(beam_df["window_start_utc"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    _emit_progress(progress, "Aggregating UE data into 5-minute windows", "ETA 5-15s")
    aggregated_ue = _aggregate_ue(ue_df)

    _emit_progress(progress, "Joining beam KPIs with UE aggregates", "ETA 2-6s")
    joined = beam_df.merge(aggregated_ue, on=["window_start_utc", "cell_id", "beam_id"], how="left")
    fill_zero_columns = [
        "ue_row_count",
        "distinct_ue_count",
        "ue_avg_sinr_db",
        "ue_avg_bler_dl_pct",
        "ue_avg_dl_throughput_mbps",
        "ue_avg_ul_throughput_mbps",
        "ue_avg_latency_ms",
        "ue_avg_packet_loss_pct",
        "ue_avg_velocity_kph",
        "ue_avg_jitter_ms",
        "ue_avg_harq_retx_pct",
        "ue_avg_traffic_load_mb",
        "ue_handover_ratio",
        "ue_low_quality_count",
        "ue_high_bler_count",
        "ue_high_latency_count",
    ]
    joined[fill_zero_columns] = joined[fill_zero_columns].fillna(0)

    _emit_progress(progress, "Engineering telecom features", "ETA 2-5s")
    joined = engineer_features(joined)
    _emit_progress(progress, "Detecting anomalies", "ETA 2-5s")
    joined = detect_anomalies(joined)
    _emit_progress(progress, "Classifying incidents and severity", "ETA 2-5s")
    joined = classify_incidents(joined)
    joined["time_window"] = joined["window_start_utc"]
    joined["affected_ue_count"] = joined["bad_ue_count"]
    joined["severity_rank"] = _severity_rank(joined["severity"])

    joined.to_csv(OUTPUT_DIR / "joined_analysis.csv", index=False)

    incidents = joined[
        [
            "time_window",
            "cell_id",
            "beam_id",
            "diagnosis",
            "severity",
            "affected_ue_count",
            "beam_health_score",
            "short_summary",
            "recommended_action",
            "avg_sinr_db",
            "avg_rsrp_dbm",
            "avg_bler_dl_pct",
            "prb_utilization_pct",
            "ue_avg_latency_ms",
            "ue_avg_packet_loss_pct",
            "congestion_score",
            "coverage_score",
            "interference_risk_score",
            "mobility_stress_score",
            "reliability_score",
            "severity_rank",
        ]
    ].copy()
    incidents.to_csv(OUTPUT_DIR / "incidents_summary.csv", index=False)

    _emit_progress(progress, f"Selecting top {top_n_incidents} incidents for LLM enrichment", "ETA 1-3s")
    llm_input = (
        incidents.sort_values(["severity_rank", "beam_health_score"], ascending=[False, True])
        .head(top_n_incidents)
        .drop(columns=["severity_rank"])
        .to_dict(orient="records")
    )
    save_json(OUTPUT_DIR / "llm_input.json", llm_input)

    enriched_payload = []
    llm_used = False
    if enrich_with_llm and llm_input:
        _emit_progress(progress, f"Running Ollama enrichment for {len(llm_input)} incidents", f"ETA {max(1, len(llm_input))}-{max(3, len(llm_input) * 3)} min")
    for index, incident in enumerate(llm_input, start=1):
        if enrich_with_llm:
            remaining = len(llm_input) - index
            _emit_progress(progress, f"Ollama incident {index}/{len(llm_input)}", f"ETA {max(0, remaining)}-{max(1, remaining * 3)} min")
        enriched, used = enrich_incident_with_ollama(incident) if enrich_with_llm else ({}, False)
        llm_used = llm_used or used
        enriched_payload.append({**incident, **(enriched or {})})

    save_json(OUTPUT_DIR / "llm_enriched_incidents.json", enriched_payload)
    _emit_progress(progress, "Building markdown report", "ETA 1-3s")
    report_markdown = build_markdown_report(incidents, OUTPUT_DIR / "top_incidents_report.md")
    total_seconds = perf_counter() - started_at
    _emit_progress(progress, f"Analysis complete in {total_seconds:.1f}s", "ETA 0s")
    return AnalysisArtifacts(len(ue_df), len(beam_df), joined, incidents, llm_input, enriched_payload, report_markdown, llm_used)


def print_example_incidents(limit: int = 5) -> None:
    incidents = pd.read_csv(OUTPUT_DIR / "incidents_summary.csv")
    print(incidents.head(limit).to_string(index=False))


def show_diagnosis_distribution() -> None:
    incidents = pd.read_csv(OUTPUT_DIR / "incidents_summary.csv")
    print(incidents["diagnosis"].value_counts().sort_values(ascending=False).to_string())


def report_top_unhealthy_beams(limit: int = 10) -> None:
    incidents = pd.read_csv(OUTPUT_DIR / "incidents_summary.csv")
    top = incidents.sort_values(["beam_health_score", "affected_ue_count"]).head(limit)
    print(top[["time_window", "cell_id", "beam_id", "diagnosis", "severity", "beam_health_score"]].to_string(index=False))
