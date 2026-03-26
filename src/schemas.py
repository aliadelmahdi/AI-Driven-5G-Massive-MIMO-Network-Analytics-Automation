from __future__ import annotations

from pydantic import BaseModel, Field


class DatabaseLoadRequest(BaseModel):
    force_reload: bool = Field(default=False)


class AnalyzeRequest(DatabaseLoadRequest):
    enrich_with_llm: bool = Field(default=False)
    top_n_incidents: int = Field(default=25, ge=5, le=100)


class PipelineResponse(BaseModel):
    status: str
    message: str
    ue_rows: int
    beam_rows: int
    incidents: int
    output_dir: str
    llm_used: bool
    report_path: str
