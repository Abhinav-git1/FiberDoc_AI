"""Pydantic schemas. JSON is camelCase to match frontend/src/types.ts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

Severity = Literal["high", "medium", "low"]
Decision = Literal["pending", "approved", "rejected", "changes_requested"]
FindingSource = Literal["rule", "ai"]


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
    doc_name: str
    title: str
    severity: Severity
    source: FindingSource
    rule_id: str
    rule_text: str
    evidence: EvidenceOut | None
    explanation: str
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
