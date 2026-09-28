"""Finding models and local persistence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class FindingType(str, Enum):
    TERMINOLOGY = "terminology_inconsistency"
    DUPLICATE = "duplicate_or_overlapping"
    STALE = "potentially_stale"
    CONTRADICTION = "contradiction"
    STYLE_GUIDE = "style_guide_violation"
    QUALITY = "general_documentation_quality"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    APPLIED = "applied"


class Evidence(BaseModel):
    text: str
    location: str | None = None
    document_id: str | None = None
    document_title: str | None = None


class StyleGuideReference(BaseModel):
    section: str | None = None
    rule: str | None = None


class ProposedChange(BaseModel):
    document_id: str
    before: str | None = None
    after: str | None = None
    description: str | None = None


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: FindingType
    severity: Severity = Severity.MEDIUM
    confidence: Confidence = Confidence.MEDIUM
    document_id: str | None = None
    document_title: str | None = None
    related_document_ids: list[str] = Field(default_factory=list)
    description: str
    evidence: list[Evidence] = Field(default_factory=list)
    style_guide_reference: StyleGuideReference | None = None
    suggested_action: str | None = None
    proposed_change: ProposedChange | None = None
    status: ReviewStatus = ReviewStatus.PENDING
    analysis_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, value: Any) -> Any:
        if isinstance(value, FindingType):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
            aliases = {
                "style": FindingType.STYLE_GUIDE,
                "style_guide_violation": FindingType.STYLE_GUIDE,
                "terminology": FindingType.TERMINOLOGY,
                "terminology_inconsistency": FindingType.TERMINOLOGY,
                "duplicate": FindingType.DUPLICATE,
                "duplicate_or_overlapping": FindingType.DUPLICATE,
                "stale": FindingType.STALE,
                "potentially_stale": FindingType.STALE,
                "contradiction": FindingType.CONTRADICTION,
                "quality": FindingType.QUALITY,
                "general_documentation_quality": FindingType.QUALITY,
                "general_documentation_quality_observation": FindingType.QUALITY,
            }
            if normalized in aliases:
                return aliases[normalized]
            try:
                return FindingType(normalized)
            except ValueError:
                return FindingType.QUALITY
        return value


class AnalysisResult(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    analysis_types: list[str] = Field(default_factory=list)
    document_count: int = 0
    model: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    notes: str | None = None


class FindingsStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings_dir = root / "findings"
        self.analyses_dir = root / "analyses"
        self.findings_dir.mkdir(parents=True, exist_ok=True)
        self.analyses_dir.mkdir(parents=True, exist_ok=True)
        self.latest_path = self.findings_dir / "latest.json"

    def save_analysis(self, result: AnalysisResult) -> Path:
        for finding in result.findings:
            finding.analysis_id = result.id
        path = self.analyses_dir / f"{result.id}.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        self.latest_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_latest(self) -> AnalysisResult | None:
        if not self.latest_path.is_file():
            return None
        return AnalysisResult.model_validate_json(
            self.latest_path.read_text(encoding="utf-8")
        )

    def load_analysis(self, analysis_id: str) -> AnalysisResult | None:
        path = self.analyses_dir / f"{analysis_id}.json"
        if not path.is_file():
            return None
        return AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))

    def update_finding_status(
        self,
        finding_id: str,
        status: ReviewStatus,
        *,
        analysis: AnalysisResult | None = None,
    ) -> AnalysisResult:
        result = analysis or self.load_latest()
        if result is None:
            raise FileNotFoundError("No analysis results found.")
        for finding in result.findings:
            if finding.id == finding_id:
                finding.status = status
                break
        else:
            raise KeyError(f"Finding not found: {finding_id}")
        self.save_analysis(result)
        return result

    def filter_findings(
        self,
        *,
        status: ReviewStatus | None = None,
        finding_type: FindingType | None = None,
        analysis: AnalysisResult | None = None,
    ) -> list[Finding]:
        result = analysis or self.load_latest()
        if result is None:
            return []
        findings = result.findings
        if status is not None:
            findings = [f for f in findings if f.status == status]
        if finding_type is not None:
            findings = [f for f in findings if f.type == finding_type]
        return findings
