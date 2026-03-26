from __future__ import annotations

import numpy as np
import pandas as pd


def engineer_features(joined: pd.DataFrame) -> pd.DataFrame:
    joined = joined.copy()
    joined["bad_ue_count"] = (
        joined["ue_low_quality_count"] + joined["ue_high_bler_count"] + joined["ue_high_latency_count"]
    ).div(3).round().astype(int)
    joined["bad_ue_ratio"] = (joined["bad_ue_count"] / joined["ue_row_count"].clip(lower=1)).clip(0, 1)
    joined["avg_ue_sinr_db"] = joined["ue_avg_sinr_db"]
    joined["avg_ue_bler_pct"] = joined["ue_avg_bler_dl_pct"]
    joined["avg_ue_dl_mbps"] = joined["ue_avg_dl_throughput_mbps"]
    joined["avg_ue_ul_mbps"] = joined["ue_avg_ul_throughput_mbps"]
    joined["avg_latency_ms"] = joined["ue_avg_latency_ms"]
    joined["avg_packet_loss_pct"] = joined["ue_avg_packet_loss_pct"]
    joined["mobility_stress_score"] = np.clip(
        0.5 * joined["ue_handover_ratio"] * 100 + 0.35 * joined["ue_avg_velocity_kph"] + 2.0 * joined["handover_failures"],
        0,
        100,
    )
    joined["congestion_score"] = np.clip(
        0.55 * joined["prb_utilization_pct"] + 0.15 * joined["beam_utilization_pct"] + 0.2 * joined["scheduler_pressure_score"] + 22 * joined["bad_ue_ratio"],
        0,
        100,
    )
    joined["coverage_score"] = np.clip(
        (-(joined["avg_rsrp_dbm"] + 70) * 1.4) + (-(joined["avg_sinr_db"] - 10) * 2.1) + joined["cell_edge_ue_ratio"] * 38,
        0,
        100,
    )
    joined["interference_risk_score"] = np.clip(
        0.6 * joined["interference_score"] + 0.45 * np.maximum(0, 12 - joined["avg_sinr_db"]) * 4 + 0.15 * joined["avg_rsrq_db"].abs(),
        0,
        100,
    )
    joined["reliability_score"] = np.clip(
        100 - (1.8 * joined["avg_bler_dl_pct"] + 1.7 * joined["ue_avg_packet_loss_pct"] + 0.8 * joined["dl_retransmission_pct"] + 2.8 * joined["radio_link_failure_count"]),
        0,
        100,
    )
    joined["user_experience_score"] = np.clip(
        100 - (1.7 * joined["bad_ue_ratio"] * 100 + 0.55 * joined["avg_latency_ms"] + 1.2 * joined["avg_packet_loss_pct"] + 0.9 * joined["avg_bler_dl_pct"]),
        0,
        100,
    )
    joined["beam_health_score"] = np.clip(
        0.35 * joined["reliability_score"] + 0.35 * joined["user_experience_score"] + 0.15 * (100 - joined["congestion_score"]) + 0.15 * (100 - joined["interference_risk_score"]),
        0,
        100,
    )
    return joined
