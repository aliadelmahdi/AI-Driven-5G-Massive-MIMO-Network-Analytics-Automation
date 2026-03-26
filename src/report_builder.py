from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_markdown_report(incidents: pd.DataFrame, path: Path) -> str:
    top = incidents.sort_values(["severity_rank", "beam_health_score"], ascending=[False, True]).head(15)
    lines = [
        "# Telecom AI Top Incidents",
        "",
        f"Generated incidents: {len(incidents)}",
        "",
        "| Time Window | Cell | Beam | Diagnosis | Severity | Health | Summary |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in top.itertuples(index=False):
        lines.append(
            f"| {row.time_window} | {row.cell_id} | {row.beam_id} | {row.diagnosis} | {row.severity} | {row.beam_health_score:.1f} | {row.short_summary} |"
        )
    content = "\n".join(lines) + "\n"
    path.write_text(content, encoding="utf-8")
    return content
