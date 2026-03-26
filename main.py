from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path
from time import perf_counter
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from src.analyze_data import analyze_datasets, print_example_incidents, report_top_unhealthy_beams, show_diagnosis_distribution
from src.api import export_static_dashboard
from src.db import bootstrap_database_from_csvs


def print_status(step: str, eta: str) -> None:
    print(f"[status] {step} | {eta}", flush=True)


def _healthcheck_host(host: str) -> str:
    if host in {"0.0.0.0", "::", ""}:
        return "127.0.0.1"
    return host


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((_healthcheck_host(host), port), timeout=1):
            return True
    except OSError:
        return False


def _telecom_api_is_running(host: str, port: int) -> bool:
    health_url = f"http://{_healthcheck_host(host)}:{port}/health"
    try:
        with urlopen(health_url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False

    return payload.get("status") == "ok" and payload.get("service") == "telecom-analytics"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local 5G Massive MIMO telecom analytics MVP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    load_db_parser = subparsers.add_parser("load-db")
    load_db_parser.add_argument("--force-reload", action="store_true")

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--force-reload", action="store_true")
    analyze_parser.add_argument("--enrich-with-llm", action="store_true")
    analyze_parser.add_argument("--top-n-incidents", type=int, default=25)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8010)

    export_dashboard_parser = subparsers.add_parser("export-dashboard")
    export_dashboard_parser.add_argument("--output-dir", default="docs")
    export_dashboard_parser.add_argument("--limit", type=int, default=200)

    subparsers.add_parser("example-incidents")
    subparsers.add_parser("diagnosis-distribution")
    subparsers.add_parser("top-unhealthy")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command_started = perf_counter()

    if args.command == "load-db":
        print_status("Loading existing telecom CSVs into MySQL", "ETA 10-30s")
        counts = bootstrap_database_from_csvs(force_reload=args.force_reload, progress=print_status)
        print(f"Loaded UE rows: {counts['ue_rows']}")
        print(f"Loaded beam KPI rows: {counts['beam_rows']}")
    elif args.command == "analyze":
        print_status("Starting telecom analysis pipeline", "ETA 20s to 5 min")
        artifacts = analyze_datasets(
            enrich_with_llm=args.enrich_with_llm,
            top_n_incidents=args.top_n_incidents,
            force_reload_db=args.force_reload,
            progress=print_status,
        )
        print(f"Joined rows: {len(artifacts.joined)}")
        print(f"Incidents rows: {len(artifacts.incidents)}")
        print(f"LLM used: {artifacts.llm_used}")
    elif args.command == "serve":
        if _port_is_open(args.host, args.port):
            if _telecom_api_is_running(args.host, args.port):
                print_status(
                    f"Telecom API already running on {_healthcheck_host(args.host)}:{args.port}",
                    "ETA 0s",
                )
                return

            raise SystemExit(
                f"[error] Port {args.port} is already in use by another process. "
                f"Stop that process or run with a different port, for example: "
                f"main.py serve --host {args.host} --port {args.port + 1}"
            )

        print_status(f"Starting API server on {args.host}:{args.port}", "ETA 2-5s")
        uvicorn.run("src.api:app", host=args.host, port=args.port, reload=False)
    elif args.command == "export-dashboard":
        print_status("Exporting static dashboard files for GitHub Pages", "ETA 1-3s")
        exported_dir = export_static_dashboard(Path(args.output_dir), limit=args.limit)
        print(f"Static dashboard exported to: {exported_dir}")
        print(f"Open locally: {exported_dir / 'index.html'}")
    elif args.command == "example-incidents":
        print_example_incidents()
    elif args.command == "diagnosis-distribution":
        show_diagnosis_distribution()
    elif args.command == "top-unhealthy":
        report_top_unhealthy_beams()

    if args.command != "serve":
        print(f"[done] {args.command} finished in {perf_counter() - command_started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
