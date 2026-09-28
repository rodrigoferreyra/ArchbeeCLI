"""Analysis orchestration — keeps Gemini/prompts separate from CLI."""

from __future__ import annotations

from archbee_cli.documents.store import DocumentStore
from archbee_cli.errors import StoreError
from archbee_cli.findings.models import (
    AnalysisResult,
    Confidence,
    Evidence,
    Finding,
    FindingType,
    FindingsStore,
    ProposedChange,
    Severity,
    StyleGuideReference,
)
from archbee_cli.gemini.client import GeminiClient
from archbee_cli.gemini.schemas import GeminiAnalysisResponse, GeminiFinding
from archbee_cli.logging_setup import get_logger
from archbee_cli.style_guide.loader import load_style_guide

logger = get_logger(__name__)

ALL_ANALYSIS_TYPES = ["terminology", "duplicates", "stale", "style"]


def _map_finding(raw: GeminiFinding) -> Finding:
    style_ref = None
    if raw.style_guide_reference is not None:
        style_ref = StyleGuideReference(
            section=raw.style_guide_reference.section,
            rule=raw.style_guide_reference.rule,
        )

    # Enforce style-guide authority: demote style findings without a reference.
    finding_type = FindingType(raw.type)
    if finding_type == FindingType.STYLE_GUIDE and (
        style_ref is None or (not style_ref.section and not style_ref.rule)
    ):
        finding_type = FindingType.QUALITY
        logger.debug(
            "Demoted style finding without style-guide reference to quality observation"
        )

    proposed = None
    if raw.proposed_change is not None:
        proposed = ProposedChange(
            document_id=raw.proposed_change.document_id,
            before=raw.proposed_change.before,
            after=raw.proposed_change.after,
            description=raw.proposed_change.description,
        )

    return Finding(
        type=finding_type,
        severity=Severity(raw.severity),
        confidence=Confidence(raw.confidence),
        document_id=raw.document_id,
        document_title=raw.document_title,
        related_document_ids=list(raw.related_document_ids or []),
        description=raw.description,
        evidence=[
            Evidence(
                text=item.text,
                location=item.location,
                document_id=item.document_id,
                document_title=item.document_title,
            )
            for item in raw.evidence
        ],
        style_guide_reference=style_ref,
        suggested_action=raw.suggested_action,
        proposed_change=proposed,
    )


def convert_gemini_response(
    response: GeminiAnalysisResponse,
    *,
    analysis_types: list[str],
    document_count: int,
    model: str,
) -> AnalysisResult:
    findings = [_map_finding(item) for item in response.findings]
    return AnalysisResult(
        analysis_types=analysis_types,
        document_count=document_count,
        model=model,
        findings=findings,
        notes=response.notes,
    )


class AnalysisRunner:
    def __init__(
        self,
        *,
        document_store: DocumentStore,
        findings_store: FindingsStore,
        gemini: GeminiClient,
        style_guide_path,
    ) -> None:
        self.document_store = document_store
        self.findings_store = findings_store
        self.gemini = gemini
        self.style_guide_path = style_guide_path

    def run(
        self,
        *,
        analysis_types: list[str] | None = None,
        document_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> AnalysisResult:
        types = analysis_types or ALL_ANALYSIS_TYPES
        style_guide = load_style_guide(self.style_guide_path)

        documents = self.document_store.list_documents()
        if not documents:
            raise StoreError(
                "No local documents found.",
                hint="Run `ArchbeeCLI pull` before analyzing.",
            )
        if document_ids:
            wanted = set(document_ids)
            documents = [d for d in documents if d.id in wanted]
        if limit is not None:
            documents = documents[:limit]

        logger.info(
            "Starting analysis types=%s documents=%d style_guide=%s",
            ",".join(types),
            len(documents),
            style_guide.path,
        )
        logger.warning(
            "Document content and the style guide will be sent to Gemini for analysis."
        )

        raw = self.gemini.analyze_documents(
            documents=documents,
            style_guide=style_guide,
            analysis_types=types,
        )
        result = convert_gemini_response(
            raw,
            analysis_types=types,
            document_count=len(documents),
            model=self.gemini.model,
        )
        self.findings_store.save_analysis(result)
        logger.info("Analysis complete: %d findings", len(result.findings))
        return result
