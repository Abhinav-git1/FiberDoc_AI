"""Pydantic schemas. JSON is camelCase to match frontend/src/types.ts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

Severity = Literal["high", "medium", "low"]
Decision = Literal["pending", "approved", "rejected", "changes_requested"]
FindingSource = Literal["rule", "ai"]
FindingStatus = Literal["passed", "failed", "missing_evidence", "needs_review"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class CommentOut(CamelModel):
    id: str
    author: str
    text: str
    at: str


class EvidenceOut(CamelModel):
    page: int
    quote: str


class FindingOut(CamelModel):
    id: str
    project_id: str
    document_id: str
    doc_name: str
    title: str
    severity: Severity
    source: FindingSource
    rule_id: str
    rule_text: str
    rule_section: str | None = None  # catalogue section of the rule, e.g. "Construction"; groups the results
    evidence: EvidenceOut | None  # first item of evidence_list (kept for older clients)
    evidence_list: list[EvidenceOut]
    explanation: str
    # None on findings created before these fields existed.
    status: FindingStatus | None = None
    source_pages_checked: list[int] | None = None
    recommended_action: str | None = None
    needs_human_review: bool | None = None
    retrieval: dict | None = None
    decision: Decision
    comments: list[CommentOut]


class ProjectOut(CamelModel):
    id: str
    name: str
    location: str
    doc_count: int


class ProjectIn(CamelModel):
    name: str
    location: str = ""


class DocumentOut(CamelModel):
    id: str
    project_id: str
    name: str
    doc_type: str
    status: str
    page_count: int
    error: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None  # of the stored original; None if the file is gone
    created_at: datetime | None = None


class StepTimingOut(CamelModel):
    name: str  # parse, embed_chunks, or a workflow node (classify, retrieve_rules, validate_evidence, ...)
    seconds: float


class LlmCallOut(CamelModel):
    op: str  # e.g. "embed 8 texts", "generate EvidenceCheck"
    seconds: float  # including retries and back-off
    attempts: int
    errors: list[str] = []
    failed: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None


class TimingsOut(CamelModel):
    """Where one document's processing time went (app/services/timing.py)."""
    total_s: float
    steps: list[StepTimingOut]
    llm_calls: list[LlmCallOut]


class AutomationSettingsOut(CamelModel):
    enabled: bool
    webhook_url: str | None
    recipient_email: str | None
    secret: str  # shown so it can be pasted into n8n's Header Auth credential (local, single-user app)
    updated_at: datetime


class AutomationSettingsIn(CamelModel):
    enabled: bool
    webhook_url: str | None = None
    recipient_email: str | None = None


class DeliveryOut(CamelModel):
    id: str
    document_id: str | None
    document_name: str | None = None
    event: str
    url: str
    status: str  # sent | failed
    http_status: int | None
    attempts: int
    error: str | None
    created_at: datetime


class ChatIn(CamelModel):
    title: str = "New chat"
    project_id: str | None = None


class ChatSummaryOut(CamelModel):
    id: str
    title: str
    project_id: str | None
    created_at: datetime
    updated_at: datetime


class MessageIn(CamelModel):
    role: Literal["user", "assistant"]
    text: str
    # `upload` and `result` messages are written only by the backend, so a client can't fake a check result.
    kind: Literal["text", "error"] = "text"


class MessageOut(CamelModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    kind: Literal["text", "upload", "result", "error"]
    document_id: str | None
    created_at: datetime


class ChatOut(ChatSummaryOut):
    messages: list[MessageOut]
    documents: list[DocumentOut]  # every document the messages refer to, to rebuild the result panel


class ReviewIn(CamelModel):
    decision: Decision
    comment: str = ""


# --- LLM structured output -------------------------------------------------
class EvidenceCheck(BaseModel):
    """What the LLM must return for a semantic rule. It may not invent values."""

    found_relevant_text: bool
    quote: str | None = None  # must be a verbatim substring of the supplied text
    page: int | None = None
    complies: Literal["yes", "no", "unclear"] = "unclear"
    explanation: str


class DocClassification(BaseModel):
    doc_type: Literal["construction_plan", "design_summary", "as_built", "permit", "test_report", "other"]
