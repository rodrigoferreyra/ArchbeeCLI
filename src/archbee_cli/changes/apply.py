"""Apply explicitly approved proposed changes to Archbee."""

from __future__ import annotations

from archbee_cli.archbee.client import ArchbeeClient
from archbee_cli.documents.store import DocumentStore, content_hash
from archbee_cli.errors import ApprovalRequiredError, ArchbeeCLIError
from archbee_cli.findings.models import Finding, FindingsStore, ReviewStatus
from archbee_cli.logging_setup import get_logger

logger = get_logger(__name__)


def apply_finding(
    *,
    finding: Finding,
    archbee: ArchbeeClient,
    document_store: DocumentStore,
    findings_store: FindingsStore,
    approved: bool,
) -> Finding:
    """Push a proposed change only when `approved` is True and status is accepted."""
    if not approved:
        raise ApprovalRequiredError(
            "Refusing to write to Archbee without explicit approval.",
            hint="Pass --approve after reviewing the proposed change.",
        )
    if finding.status == ReviewStatus.REJECTED:
        raise ApprovalRequiredError(
            "Rejected findings cannot be applied.",
            hint="Re-review the finding if you intend to apply it.",
        )
    if finding.status not in (ReviewStatus.ACCEPTED, ReviewStatus.PENDING):
        raise ApprovalRequiredError(
            f"Finding status is '{finding.status.value}'; expected accepted.",
            hint="Accept the finding in `ArchbeeCLI review` first.",
        )
    if finding.status == ReviewStatus.PENDING:
        raise ApprovalRequiredError(
            "Finding has not been accepted yet.",
            hint="Accept it in `ArchbeeCLI review`, then apply with --approve.",
        )
    change = finding.proposed_change
    if change is None or not change.after:
        raise ArchbeeCLIError(
            "This finding has no proposed change payload to apply.",
        )

    doc_id = change.document_id or finding.document_id
    if not doc_id:
        raise ArchbeeCLIError("Proposed change is missing a document ID.")

    local = document_store.get_document(doc_id)
    if local is None:
        raise ArchbeeCLIError(
            f"Local document {doc_id} not found.",
            hint="Run `ArchbeeCLI pull` and retry.",
        )

    # Prefer full-document replacement when `after` looks like full content;
    # otherwise apply a simple before→after substitution when possible.
    new_content = change.after
    if change.before and change.before in local.content:
        new_content = local.content.replace(change.before, change.after, 1)
    elif change.after and change.after.strip() == change.after and "\n" not in change.after:
        # Short snippet without match — refuse rather than overwrite whole doc.
        if change.before and change.before not in local.content:
            raise ArchbeeCLIError(
                "Could not locate the proposed 'before' text in the local document.",
                hint="Re-run analysis or edit the proposed change.",
            )

    logger.info("Updating Archbee document %s after explicit approval", doc_id)
    result = archbee.update_document(doc_id=doc_id, content=new_content, fmt="markdown")
    logger.info("Archbee update OK docId=%s newRecord=%s", result.doc_id, result.new_record)

    # Refresh local snapshot for this document only.
    local.content = new_content
    local.content_hash = content_hash(new_content)
    docs = document_store.list_documents()
    for i, doc in enumerate(docs):
        if doc.id == doc_id:
            docs[i] = local
            break
    document_store.replace_snapshot(space_id=local.space_id or archbee.space_id, documents=docs)

    findings_store.update_finding_status(finding.id, ReviewStatus.APPLIED)
    finding.status = ReviewStatus.APPLIED
    return finding
