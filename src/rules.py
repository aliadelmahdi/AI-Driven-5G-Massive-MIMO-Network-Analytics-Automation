from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import DIAGNOSIS_ACTIONS


def classify_incidents(frame: pd.DataFrame) -> pd.DataFrame:
    diagnoses = []
    severities = []
    summaries = []

    for row in frame.itertuples(index=False):
        congestion = row.congestion_score >= 72 and row.prb_utilization_pct >= 82 and row.active_ue_count >= 45
        interference = row.interference_risk_score >= 68 and row.avg_rsrp_dbm > -95 and row.avg_sinr_db < 8
        coverage = row.coverage_score >= 68 and row.avg_rsrp_dbm <= -97 and row.avg_sinr_db < 9
        mobility = row.mobility_stress_score >= 62 and row.handover_failures >= 2 and row.ue_avg_velocity_kph >= 38
        reliability = row.reliability_score <= 45 or row.avg_bler_dl_pct >= 16 or row.radio_link_failure_count >= 3
        active_causes = sum([congestion, interference, coverage, mobility, reliability])

        if active_causes == 0 and row.beam_health_score >= 73 and not row.any_anomaly:
            diagnosis = "healthy"
        elif active_causes >= 2:
            diagnosis = "mixed_problem"
        elif congestion:
            diagnosis = "congestion"
        elif interference:
            diagnosis = "interference"
        elif coverage:
            diagnosis = "coverage_issue"
        elif mobility:
            diagnosis = "mobility_instability"
        else:
            diagnosis = "reliability_degradation"

        if diagnosis == "healthy":
            severity = "low" if row.beam_health_score >= 85 else "medium"
        else:
            severity_score = (
                (100 - row.beam_health_score) * 0.45
                + row.bad_ue_ratio * 100 * 0.25
                + row.avg_bler_dl_pct
                + row.handover_failures * 2.5
                + (12 if row.any_anomaly else 0)
            )
            severity = np.select(
                [severity_score >= 78, severity_score >= 58, severity_score >= 35],
                ["critical", "high", "medium"],
                default="low",
            ).item()

        summary = (
            f"{diagnosis.replace('_', ' ')} on {row.cell_id}/{row.beam_id}: "
            f"SINR {row.avg_sinr_db:.1f} dB, BLER {row.avg_bler_dl_pct:.1f}%, "
            f"PRB {row.prb_utilization_pct:.1f}%, affected UE ratio {row.bad_ue_ratio:.0%}."
        )
        diagnoses.append(diagnosis)
        severities.append(severity)
        summaries.append(summary)

    frame = frame.copy()
    frame["diagnosis"] = diagnoses
    frame["severity"] = severities
    frame["recommended_action"] = frame["diagnosis"].map(DIAGNOSIS_ACTIONS)
    frame["short_summary"] = summaries
    return frame
