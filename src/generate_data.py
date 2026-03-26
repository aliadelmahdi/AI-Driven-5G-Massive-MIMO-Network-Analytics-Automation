from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .utils import DATA_DIR, DEVICE_PROFILES, SCENARIO_PROFILES, SEED, SERVICE_PROFILES, ensure_directories


@dataclass
class GenerationConfig:
    ue_rows: int = 150_000
    beam_rows_target: int = 15_000
    seed: int = SEED
    num_cells: int = 8
    beams_per_cell: int = 6
    num_ues: int = 2_000
    days: int = 7


def _build_beam_windows(config: GenerationConfig, rng: np.random.Generator) -> pd.DataFrame:
    windows = pd.date_range("2026-03-01", periods=config.days * 24 * 12, freq="5min", tz="UTC")
    cells = [f"CELL_{index:02d}" for index in range(1, config.num_cells + 1)]
    beams = [f"B{index:02d}" for index in range(1, config.beams_per_cell + 1)]
    grid = pd.MultiIndex.from_product([windows, cells, beams], names=["window_start_utc", "cell_id", "beam_id"]).to_frame(index=False)

    hours = grid["window_start_utc"].dt.hour.to_numpy()
    weekend_factor = np.where(grid["window_start_utc"].dt.dayofweek.to_numpy() >= 5, 0.88, 1.0)
    diurnal = 0.55 + 0.45 * np.sin((hours - 7) / 24 * 2 * np.pi) ** 2
    scenario_choices = np.array(
        ["healthy", "congested", "interference_heavy", "weak_coverage", "mobility_instability", "sudden_degradation", "mixed_cause"]
    )
    scenario_weights = np.array([0.52, 0.16, 0.09, 0.08, 0.06, 0.03, 0.06])
    grid["scenario"] = rng.choice(scenario_choices, size=len(grid), p=scenario_weights)
    profile_shifts = grid["scenario"].map(SCENARIO_PROFILES)

    base_ues = 18 + (diurnal * 44 * weekend_factor) + rng.normal(0, 4.5, len(grid))
    base_ues += np.where(grid["scenario"].eq("congested"), 24, 0)
    base_ues += np.where(grid["scenario"].eq("mixed_cause"), 18, 0)
    active_ue_count = np.clip(np.round(base_ues), 6, 96)

    distance_bucket = rng.uniform(0.2, 1.0, len(grid))
    cell_edge_ratio = np.clip(0.12 + 0.52 * distance_bucket + np.where(grid["scenario"].eq("weak_coverage"), 0.16, 0.0), 0.05, 0.95)
    rsrp = -76 - 26 * distance_bucket + np.array([entry["rsrp_shift"] for entry in profile_shifts]) + rng.normal(0, 2.2, len(grid))
    sinr = 20 - 17 * distance_bucket + np.array([entry["sinr_shift"] for entry in profile_shifts]) + rng.normal(0, 1.8, len(grid))
    rsrq = -8.2 - 4.8 * distance_bucket + 0.12 * sinr + rng.normal(0, 1.0, len(grid))
    prb_util = np.clip(26 + active_ue_count * 0.72 + np.array([entry["prb_shift"] for entry in profile_shifts]) + rng.normal(0, 6.5, len(grid)), 10, 100)
    beam_util = np.clip(prb_util * rng.uniform(0.83, 1.02, len(grid)) + rng.normal(0, 3, len(grid)), 8, 100)
    interference = np.clip(32 - 0.9 * sinr + np.where(grid["scenario"].eq("interference_heavy"), 18, 0) + rng.normal(0, 5, len(grid)), 0, 100)
    bler = np.clip(2 + (18 - sinr) * 0.62 + (prb_util - 50).clip(min=0) * 0.06 + np.array([entry["bler_shift"] for entry in profile_shifts]) + rng.normal(0, 1.6, len(grid)), 0.3, 28)
    scheduled_dl = np.clip(24 + sinr * 2.7 + (100 - prb_util) * 0.55 - bler * 0.7 + rng.normal(0, 9, len(grid)), 5, 240)
    scheduled_ul = np.clip(6 + sinr * 0.75 + (100 - prb_util) * 0.18 - bler * 0.22 + rng.normal(0, 3, len(grid)), 1, 70)
    handover_attempts = np.clip(np.round(active_ue_count * (0.03 + cell_edge_ratio * 0.08) + np.array([entry["handover_shift"] for entry in profile_shifts]) + rng.normal(0, 1.3, len(grid))), 0, None)
    handover_failures = np.clip(np.round(handover_attempts * np.clip(0.03 + bler * 0.012 + np.where(grid["scenario"].eq("mobility_instability"), 0.16, 0), 0.01, 0.55)), 0, None)
    beam_switch_success = np.clip(99 - bler * 0.8 - handover_failures * 0.6 + rng.normal(0, 1.4, len(grid)), 62, 100)
    rlf = np.clip(np.round(handover_failures * 0.25 + np.where(grid["scenario"].isin(["weak_coverage", "sudden_degradation", "mixed_cause"]), 1.8, 0) + rng.normal(0, 0.9, len(grid))), 0, None)
    power_headroom = np.clip(19 + sinr * 0.12 - prb_util * 0.05 + rng.normal(0, 1.1, len(grid)), -4, 23)
    scheduler_pressure = np.clip(0.62 * prb_util + 0.22 * active_ue_count + 0.28 * bler + rng.normal(0, 4, len(grid)), 0, 100)

    return pd.DataFrame(
        {
            "window_start_utc": grid["window_start_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cell_id": grid["cell_id"],
            "beam_id": grid["beam_id"],
            "active_ue_count": active_ue_count.astype(int),
            "avg_rsrp_dbm": np.round(rsrp, 2),
            "avg_rsrq_db": np.round(rsrq, 2),
            "avg_sinr_db": np.round(sinr, 2),
            "prb_utilization_pct": np.round(prb_util, 2),
            "beam_utilization_pct": np.round(beam_util, 2),
            "dl_retransmission_pct": np.round(np.clip(bler * 0.8 + rng.normal(0, 0.8, len(grid)), 0.2, 30), 2),
            "scheduled_dl_mbps": np.round(scheduled_dl, 2),
            "scheduled_ul_mbps": np.round(scheduled_ul, 2),
            "avg_bler_dl_pct": np.round(bler, 2),
            "handover_attempts": handover_attempts.astype(int),
            "handover_failures": handover_failures.astype(int),
            "beam_switch_success_rate_pct": np.round(beam_switch_success, 2),
            "radio_link_failure_count": rlf.astype(int),
            "cell_edge_ue_ratio": np.round(cell_edge_ratio, 3),
            "interference_score": np.round(interference, 2),
            "power_headroom_db": np.round(power_headroom, 2),
            "scheduler_pressure_score": np.round(scheduler_pressure, 2),
            "scenario_label": grid["scenario"],
        }
    )


def _weighted_service_type(rng: np.random.Generator) -> str:
    return rng.choice(
        ["video_streaming", "gaming", "voice", "web_browsing", "file_download", "iot"],
        p=[0.22, 0.15, 0.15, 0.18, 0.18, 0.12],
    )


def _weighted_device_profile(service_type: str, rng: np.random.Generator) -> str:
    if service_type == "iot":
        return rng.choice(["iot_sensor", "industrial_modem"], p=[0.75, 0.25])
    if service_type == "file_download":
        return rng.choice(["fixed_wireless", "flagship_phone", "midrange_phone"], p=[0.45, 0.25, 0.30])
    return rng.choice(["flagship_phone", "midrange_phone", "fixed_wireless", "industrial_modem"], p=[0.33, 0.42, 0.10, 0.15])


def _build_ue_measurements(beam_df: pd.DataFrame, config: GenerationConfig, rng: np.random.Generator) -> pd.DataFrame:
    weights = beam_df["active_ue_count"].to_numpy(dtype=float)
    sampled = beam_df.iloc[rng.choice(len(beam_df), size=config.ue_rows, p=weights / weights.sum())].reset_index(drop=True)
    ue_ids = np.array([f"UE_{index:04d}" for index in range(1, config.num_ues + 1)])
    sampled["ue_id"] = rng.choice(ue_ids, size=config.ue_rows)

    timestamps = pd.to_datetime(sampled["window_start_utc"], utc=True) + pd.to_timedelta(rng.integers(0, 300, size=config.ue_rows), unit="s")
    service_types = np.array([_weighted_service_type(rng) for _ in range(config.ue_rows)])
    device_profiles = np.array([_weighted_device_profile(service_type, rng) for service_type in service_types])
    service_latency = np.array([SERVICE_PROFILES[name].latency_sensitivity for name in service_types])
    service_throughput = np.array([SERVICE_PROFILES[name].throughput_need for name in service_types])
    device_gain = np.array([DEVICE_PROFILES[name]["rf_gain"] for name in device_profiles])
    device_traffic = np.array([DEVICE_PROFILES[name]["traffic"] for name in device_profiles])
    cell_edge = sampled["cell_edge_ue_ratio"].to_numpy()
    mobility = np.clip(rng.gamma(shape=2.1, scale=18.0, size=config.ue_rows) + np.where(sampled["scenario_label"].eq("mobility_instability"), 42, 0), 0, 140)

    rsrp = sampled["avg_rsrp_dbm"].to_numpy() + 3.2 * (device_gain - 1.0) - cell_edge * 8 + rng.normal(0, 3, config.ue_rows)
    sinr = sampled["avg_sinr_db"].to_numpy() + 3 * (device_gain - 1.0) - cell_edge * 4.6 + rng.normal(0, 2.3, config.ue_rows)
    rsrq = sampled["avg_rsrq_db"].to_numpy() + 0.1 * sinr + rng.normal(0, 1.2, config.ue_rows)
    cqi = np.clip(np.round((sinr + 6.5) / 1.9 + rng.normal(0, 1.0, config.ue_rows)), 1, 15)
    rank_indicator = np.where(sinr > 16, 4, np.where(sinr > 10, 2, 1))
    mcs = np.clip(np.round(cqi * 1.8 + 1.2 * rank_indicator + rng.normal(0, 2.1, config.ue_rows)), 0, 28)
    harq = np.clip(sampled["dl_retransmission_pct"].to_numpy() + np.maximum(0, 12 - sinr) * 0.6 + rng.normal(0, 1.4, config.ue_rows), 0, 38)
    bler = np.clip(sampled["avg_bler_dl_pct"].to_numpy() + np.maximum(0, 10 - sinr) * 0.6 + harq * 0.12 + rng.normal(0, 1.8, config.ue_rows), 0.1, 45)

    dl_tp = np.clip(
        7 + mcs * 1.8 + np.maximum(sinr, 0) * 0.8 + rank_indicator * 7 - bler * 0.95 - sampled["prb_utilization_pct"].to_numpy() * 0.12
        + service_throughput * 9 + device_traffic * 8 + rng.normal(0, 5.2, config.ue_rows),
        0.05,
        250,
    )
    ul_tp = np.clip(
        1.5 + mcs * 0.42 + np.maximum(sinr, 0) * 0.18 - bler * 0.22 - sampled["prb_utilization_pct"].to_numpy() * 0.03
        + device_traffic * 2.5 + rng.normal(0, 1.6, config.ue_rows),
        0.02,
        60,
    )

    packet_loss = np.clip(0.18 * bler + np.maximum(0, sampled["prb_utilization_pct"].to_numpy() - 80) * 0.07 + rng.normal(0, 0.65, config.ue_rows), 0, 35)
    latency = np.clip(
        10 + service_latency * 12 + np.maximum(0, 14 - sinr) * 2.1 + np.maximum(0, sampled["prb_utilization_pct"].to_numpy() - 70) * 0.45
        + packet_loss * 1.7 + rng.normal(0, 4.5, config.ue_rows),
        4,
        280,
    )
    jitter = np.clip(2 + service_latency * 4 + packet_loss * 0.45 + np.maximum(0, 12 - sinr) * 0.5 + rng.normal(0, 1.7, config.ue_rows), 0.4, 85)
    traffic_load = np.clip(device_traffic * service_throughput * rng.gamma(shape=2.4, scale=4.0, size=config.ue_rows), 0.05, 240)
    neighbor_count = np.clip(np.round(2 + cell_edge * 6 + rng.normal(0, 1.0, config.ue_rows)), 1, 12)
    beam_switch_count = np.clip(np.round(mobility / 32 + rng.normal(0, 1.0, config.ue_rows)), 0, 15)
    timing_advance = np.clip(50 + 620 * cell_edge + mobility * 0.7 + rng.normal(0, 35, config.ue_rows), 10, 900)
    ho_probability = np.clip(0.02 + mobility / 220 + cell_edge * 0.12 + np.where(sampled["scenario_label"].eq("mobility_instability"), 0.18, 0), 0, 0.85)
    handover_event = np.where(rng.random(config.ue_rows) < ho_probability, "yes", "no")

    return pd.DataFrame(
        {
            "timestamp_utc": timestamps.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ue_id": sampled["ue_id"],
            "serving_cell_id": sampled["cell_id"],
            "beam_id": sampled["beam_id"],
            "rsrp_dbm": np.round(rsrp, 2),
            "rsrq_db": np.round(rsrq, 2),
            "sinr_db": np.round(sinr, 2),
            "cqi": cqi.astype(int),
            "rank_indicator": rank_indicator.astype(int),
            "mcs_index": mcs.astype(int),
            "bler_dl_pct": np.round(bler, 2),
            "timing_advance": np.round(timing_advance, 2),
            "dl_throughput_mbps": np.round(dl_tp, 2),
            "ul_throughput_mbps": np.round(ul_tp, 2),
            "handover_event": handover_event,
            "velocity_kph": np.round(mobility, 2),
            "packet_loss_pct": np.round(packet_loss, 2),
            "latency_ms": np.round(latency, 2),
            "jitter_ms": np.round(jitter, 2),
            "harq_retx_pct": np.round(harq, 2),
            "device_profile": device_profiles,
            "service_type": service_types,
            "traffic_load_mb": np.round(traffic_load, 2),
            "neighbor_cell_count": neighbor_count.astype(int),
            "beam_switch_count": beam_switch_count.astype(int),
        }
    )


def generate_synthetic_data(config: GenerationConfig | None = None, force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    ensure_directories()
    config = config or GenerationConfig()
    ue_path = DATA_DIR / "ue_measurements.csv"
    beam_path = DATA_DIR / "beam_kpis.csv"

    if not force and ue_path.exists() and beam_path.exists():
        ue_df = pd.read_csv(ue_path)
        beam_df = pd.read_csv(beam_path)
        if len(ue_df) >= config.ue_rows and len(beam_df) >= config.beam_rows_target:
            return ue_df, beam_df

    rng = np.random.default_rng(config.seed)
    beam_df = _build_beam_windows(config, rng)
    ue_df = _build_ue_measurements(beam_df, config, rng)

    if len(ue_df) < config.ue_rows or len(beam_df) < config.beam_rows_target:
        raise ValueError("Generated dataset did not meet required thresholds.")

    ue_df.to_csv(ue_path, index=False)
    beam_df.drop(columns=["scenario_label"]).to_csv(beam_path, index=False)
    if ue_path.stat().st_size == 0 or beam_path.stat().st_size == 0:
        raise ValueError("Generated CSV files are empty.")
    return ue_df, beam_df
