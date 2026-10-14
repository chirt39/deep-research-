from typing import Literal

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(default="default_user", min_length=1)
    thread_id: str = Field(default="default_thread", min_length=1)
    tenant_id: str = Field(default="default_tenant", min_length=1)
    max_iterations: int | None = Field(default=None, ge=1, le=6)
    enable_memory: bool | None = None
    research_domain: Literal["auto", "general", "finance"] = "auto"


class ResearchResponse(BaseModel):
    query: str
    user_id: str
    thread_id: str
    tenant_id: str
    final: str
    usage: dict | None = None
    quality: dict | None = None
    report_id: str | None = None
    research_domain: str = "general"
    evidence_summary: dict | None = None
    trace: list[str] = Field(default_factory=list)
