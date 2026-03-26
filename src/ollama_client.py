from __future__ import annotations

import json
import os
import subprocess
from typing import Any

import requests

from .recommend import fallback_incident_text

OLLAMA_MODEL = "qwen3:8b"
OLLAMA_HTTP_URL = f"{os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')}/api/generate"

PROMPT_TEMPLATE = """
You are a senior telecom network incident analyst focused on 5G Massive MIMO beam behavior.
Use only the incident fields provided below. Do not invent causes, KPIs, or actions that are not supported.
Return strict JSON with exactly these keys:
explanation, root_cause, recommendation, alert_summary

The explanation must be plain English and concise.
The root_cause must identify the most likely cause using only the supplied metrics.
The recommendation must be an operator action, not a generic statement.
The alert_summary must be one short alert line.

Incident:
{incident_json}
""".strip()


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response.")
    return json.loads(text[start : end + 1])


def _http_generate(prompt: str, timeout: int = 120) -> str:
    response = requests.post(
        OLLAMA_HTTP_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("response", "")


def _subprocess_generate(prompt: str, timeout: int = 180) -> str:
    process = subprocess.run(
        ["ollama", "run", OLLAMA_MODEL],
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=True,
    )
    return process.stdout


def enrich_incident_with_ollama(incident: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    prompt = PROMPT_TEMPLATE.format(incident_json=json.dumps(incident, ensure_ascii=True))
    retry_suffix = "\nReturn only valid JSON. No markdown. No code fences. No extra keys."
    for attempt in range(2):
        try:
            try:
                raw = _http_generate(prompt if attempt == 0 else prompt + retry_suffix)
            except Exception:
                raw = _subprocess_generate(prompt if attempt == 0 else prompt + retry_suffix)
            parsed = _parse_json(raw)
            required = {"explanation", "root_cause", "recommendation", "alert_summary"}
            if not required.issubset(parsed):
                raise ValueError("Model output missing required keys.")
            return {key: str(parsed[key]).strip() for key in required}, True
        except Exception:
            continue
    return fallback_incident_text(incident), False
