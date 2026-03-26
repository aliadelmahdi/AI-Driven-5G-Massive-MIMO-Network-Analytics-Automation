from __future__ import annotations

import numpy as np
import pandas as pd


def detect_anomalies(joined: pd.DataFrame) -> pd.DataFrame:
    frame = joined.sort_values(["cell_id", "beam_id", "window_start_utc"]).copy()
    metrics = {
        "sinr_collapse_anomaly": ("avg_sinr_db", -1),
        "bler_spike_anomaly": ("avg_bler_dl_pct", 1),
        "prb_spike_anomaly": ("prb_utilization_pct", 1),
        "handover_failure_spike_anomaly": ("handover_failures", 1),
        "throughput_drop_anomaly": ("ue_avg_dl_throughput_mbps", -1),
        "latency_spike_anomaly": ("ue_avg_latency_ms", 1),
    }
    for column, (metric, direction) in metrics.items():
        rolling_mean = frame.groupby(["cell_id", "beam_id"])[metric].transform(lambda s: s.rolling(12, min_periods=4).mean())
        rolling_std = frame.groupby(["cell_id", "beam_id"])[metric].transform(lambda s: s.rolling(12, min_periods=4).std())
        z_score = (frame[metric] - rolling_mean) / rolling_std.replace(0, np.nan)
        frame[column] = (z_score < -2.2).fillna(False) if direction < 0 else (z_score > 2.2).fillna(False)

    frame["throughput_drop_without_load_drop"] = (
        frame["throughput_drop_anomaly"]
        & (frame["prb_utilization_pct"] > frame.groupby(["cell_id", "beam_id"])["prb_utilization_pct"].transform("median") - 5)
    )
    frame["any_anomaly"] = frame[
        [
            "sinr_collapse_anomaly",
            "bler_spike_anomaly",
            "prb_spike_anomaly",
            "handover_failure_spike_anomaly",
            "throughput_drop_without_load_drop",
            "latency_spike_anomaly",
        ]
    ].any(axis=1)
    return frame
