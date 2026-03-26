from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
N8N_DIR = PROJECT_ROOT / "n8n"
SEED = 42


@dataclass(frozen=True)
class ServiceProfile:
    name: str
    latency_sensitivity: float
    throughput_need: float
    reliability_need: float
    burstiness: float


SERVICE_PROFILES = {
    "video_streaming": ServiceProfile("video_streaming", 0.55, 1.0, 0.7, 0.8),
    "gaming": ServiceProfile("gaming", 1.0, 0.65, 0.9, 0.55),
    "voice": ServiceProfile("voice", 0.95, 0.25, 1.0, 0.35),
    "web_browsing": ServiceProfile("web_browsing", 0.45, 0.45, 0.5, 0.5),
    "file_download": ServiceProfile("file_download", 0.2, 1.1, 0.45, 0.9),
    "iot": ServiceProfile("iot", 0.5, 0.1, 0.95, 0.15),
}

DEVICE_PROFILES = {
    "flagship_phone": {"rf_gain": 1.1, "traffic": 1.0},
    "midrange_phone": {"rf_gain": 0.95, "traffic": 0.8},
    "fixed_wireless": {"rf_gain": 1.05, "traffic": 1.7},
    "industrial_modem": {"rf_gain": 1.0, "traffic": 0.7},
    "iot_sensor": {"rf_gain": 0.85, "traffic": 0.2},
}

SCENARIO_PROFILES = {
    "healthy": {"sinr_shift": 2.0, "rsrp_shift": 1.0, "prb_shift": -10, "bler_shift": -2, "handover_shift": -1},
    "congested": {"sinr_shift": -1.0, "rsrp_shift": 0.0, "prb_shift": 22, "bler_shift": 3, "handover_shift": 0},
    "interference_heavy": {"sinr_shift": -7.5, "rsrp_shift": 0.5, "prb_shift": 6, "bler_shift": 4, "handover_shift": 1},
    "weak_coverage": {"sinr_shift": -5.5, "rsrp_shift": -10.0, "prb_shift": 4, "bler_shift": 5, "handover_shift": 2},
    "mobility_instability": {"sinr_shift": -3.0, "rsrp_shift": -2.5, "prb_shift": 2, "bler_shift": 4, "handover_shift": 7},
    "sudden_degradation": {"sinr_shift": -8.5, "rsrp_shift": -6.0, "prb_shift": 18, "bler_shift": 8, "handover_shift": 4},
    "mixed_cause": {"sinr_shift": -6.5, "rsrp_shift": -4.5, "prb_shift": 14, "bler_shift": 7, "handover_shift": 4},
}

DIAGNOSIS_ACTIONS = {
    "healthy": "Monitor routinely and keep current beam scheduling policy.",
    "congestion": "Shift load, tune scheduler weights, and consider capacity expansion on this sector.",
    "interference": "Inspect PCI and beam overlap, then optimize neighbor coordination and tilt.",
    "coverage_issue": "Review coverage map, antenna alignment, and power settings for edge users.",
    "mobility_instability": "Tune handover thresholds and time-to-trigger for fast-moving users.",
    "reliability_degradation": "Inspect HARQ, retransmission trends, and transport quality for persistent errors.",
    "mixed_problem": "Run a joint RF and scheduler review because multiple degradations are interacting.",
}


def ensure_directories() -> None:
    for directory in (DATA_DIR, OUTPUT_DIR, N8N_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=True)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def clamp(value: Any, lower: float, upper: float) -> Any:
    return max(lower, min(upper, value))
