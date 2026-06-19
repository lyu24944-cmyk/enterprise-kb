from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    filename: str
    doc_type: str
    category: str
    chunk_count: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    doc_ids: list[str] = Field(default_factory=list)
    stream: bool = True


class Citation(BaseModel):
    doc_id: str
    filename: str
    page: int | None = None
    section: str | None = None
    text: str


class ChatResponse(BaseModel):
    session_id: str
    intent: str
    content: str
    citations: list[Citation] = Field(default_factory=list)


class TaskRequest(BaseModel):
    doc_id: str
    extra: dict[str, Any] = Field(default_factory=dict)


class SummaryResult(BaseModel):
    summary: str
    outline: list[str] = Field(default_factory=list)


class RiskClause(BaseModel):
    clause: str
    risk_level: str
    category: str
    suggestion: str
    location: str | None = None


class LeaveFormResult(BaseModel):
    form_markdown: str
    policy_refs: list[str] = Field(default_factory=list)
