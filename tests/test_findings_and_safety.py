"""Findings persistence, filtering, and safety tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from archbee_cli.changes.apply import apply_finding
from archbee_cli.documents.models import StoredDocument
from archbee_cli.documents.store import DocumentStore
from archbee_cli.errors import ApprovalRequiredError
from archbee_cli.findings.models import (
    AnalysisResult,
    Finding,
    FindingType,
    FindingsStore,
    ProposedChange,
    ReviewStatus,
    Severity,
)
from archbee_cli.logging_setup import RedactingFilter
import logging


def test_findings_roundtrip(tmp_path: Path) -> None:
    store = FindingsStore(tmp_path)
    result = AnalysisResult(
        findings=[
            Finding(
                type=FindingType.TERMINOLOGY,
                severity=Severity.LOW,
                description="Voice vs Teams Voice",
                evidence=[],
            )
        ]
    )
    store.save_analysis(result)
    loaded = store.load_latest()
    assert loaded is not None
    assert loaded.findings[0].description.startswith("Voice")
    store.update_finding_status(loaded.findings[0].id, ReviewStatus.REJECTED)
    again = store.load_latest()
    assert again is not None
    assert again.findings[0].status == ReviewStatus.REJECTED
    pending = store.filter_findings(status=ReviewStatus.PENDING)
    assert pending == []


def test_apply_requires_approval(tmp_path: Path) -> None:
    findings = FindingsStore(tmp_path)
    docs = DocumentStore(tmp_path)
    docs.replace_snapshot(
        space_id="space",
        documents=[
            StoredDocument(id="doc1", title="T", content="Hello world\n", space_id="space")
        ],
    )
    finding = Finding(
        type=FindingType.STYLE_GUIDE,
        description="fix casing",
        status=ReviewStatus.ACCEPTED,
        proposed_change=ProposedChange(
            document_id="doc1", before="Hello", after="Hi"
        ),
    )
    findings.save_analysis(AnalysisResult(findings=[finding]))

    class BoomClient:
        def update_document(self, **kwargs):
            raise AssertionError("update_document must not be called without approval")

    with pytest.raises(ApprovalRequiredError):
        apply_finding(
            finding=finding,
            archbee=BoomClient(),  # type: ignore[arg-type]
            document_store=docs,
            findings_store=findings,
            approved=False,
        )


def test_rejected_finding_not_applied(tmp_path: Path) -> None:
    findings = FindingsStore(tmp_path)
    docs = DocumentStore(tmp_path)
    finding = Finding(
        type=FindingType.STYLE_GUIDE,
        description="x",
        status=ReviewStatus.REJECTED,
        proposed_change=ProposedChange(document_id="doc1", after="# x"),
    )
    with pytest.raises(ApprovalRequiredError):
        apply_finding(
            finding=finding,
            archbee=object(),  # type: ignore[arg-type]
            document_store=docs,
            findings_store=findings,
            approved=True,
        )


def test_api_keys_redacted_from_logs() -> None:
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Authorization: Bearer SUPERSECRETTOKEN",
        args=(),
        exc_info=None,
    )
    filt = RedactingFilter()
    assert filt.filter(record) is True
    assert "SUPERSECRETTOKEN" not in record.getMessage()
    assert "REDACTED" in record.getMessage()
