"""Pydantic schemas for structured Gemini analysis responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GeminiEvidence(BaseModel):
    text: str = Field(description="Exact or near-exact excerpt from a document")
    location: str | None = Field(
        default=None, description="Heading/section when available"
    )
    document_id: str | None = None
    document_title: str | None = None


class GeminiStyleGuideReference(BaseModel):
    section: str | None = None
    rule: str | None = None


class GeminiProposedChange(BaseModel):
    document_id: str
    before: str | None = None
    after: str | None = None
    description: str | None = None


class GeminiFinding(BaseModel):
    type: Literal[
        "terminology_inconsistency",
        "duplicate_or_overlapping",
        "potentially_stale",
        "contradiction",
        "style_guide_violation",
        "general_documentation_quality",
    ]
    severity: Literal["info", "low", "medium", "high"] = "medium"
    confidence: Literal["low", "medium", "high"] = "medium"
    document_id: str | None = None
    document_title: str | None = None
    related_document_ids: list[str] = Field(default_factory=list)
    description: str
    evidence: list[GeminiEvidence] = Field(default_factory=list)
    style_guide_reference: GeminiStyleGuideReference | None = None
    suggested_action: str | None = None
    proposed_change: GeminiProposedChange | None = None


class GeminiAnalysisResponse(BaseModel):
    findings: list[GeminiFinding] = Field(default_factory=list)
    notes: str | None = None
