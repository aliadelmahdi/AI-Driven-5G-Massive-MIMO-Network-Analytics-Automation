from __future__ import annotations

from .utils import DIAGNOSIS_ACTIONS


def fallback_incident_text(incident: dict) -> dict:
    diagnosis = incident["diagnosis"]
    return {
        "explanation": incident["short_summary"],
        "root_cause": f"Most likely cause is {diagnosis.replace('_', ' ')} based on the provided telecom KPIs.",
        "recommendation": DIAGNOSIS_ACTIONS.get(diagnosis, "Review the beam KPIs and UE trends."),
        "alert_summary": f"{incident['severity'].upper()}: {incident['cell_id']}/{incident['beam_id']} {diagnosis.replace('_', ' ')}",
    }
