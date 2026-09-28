"""Pull Archbee Space into the local snapshot. Does not invoke Gemini."""

from __future__ import annotations

from datetime import datetime, timezone

from rich.progress import Progress, SpinnerColumn, TextColumn

from archbee_cli.archbee.client import ArchbeeClient
from archbee_cli.documents.models import PullChangeSummary, StoredDocument
from archbee_cli.documents.store import DocumentStore
from archbee_cli.logging_setup import get_logger

logger = get_logger(__name__)


def pull_space(
    *,
    client: ArchbeeClient,
    store: DocumentStore,
    force: bool = False,
    show_progress: bool = True,
) -> tuple[list[StoredDocument], PullChangeSummary]:
    """Retrieve all documents from the authenticated Space and store locally.

    `force` currently always re-downloads content; the flag is reserved for
    future incremental sync optimizations and keeps the CLI contract stable.
    """
    _ = force  # incremental sync not implemented yet; always full pull
    summaries = client.list_all_documents()
    logger.info("Found %d documents in Space", len(summaries))

    stored: list[StoredDocument] = []
    now = datetime.now(timezone.utc)

    if show_progress:
        progress_cm = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        )
    else:
        from contextlib import nullcontext

        progress_cm = nullcontext()

    with progress_cm as progress:
        task_id = None
        if progress is not None:
            task_id = progress.add_task("Downloading documents…", total=len(summaries))

        for summary in summaries:
            content = client.get_document(summary.id, fmt="markdown")
            stored.append(
                StoredDocument(
                    id=summary.id,
                    title=summary.name or summary.id,
                    content=content.content or "",
                    format=content.format or "markdown",
                    url_key=summary.url_key,
                    url_alias=summary.url_alias,
                    hidden=summary.hidden,
                    privacy=summary.privacy,
                    space_id=client.space_id,
                    retrieved_at=now,
                )
            )
            if progress is not None and task_id is not None:
                progress.advance(task_id)

    changes = store.replace_snapshot(space_id=client.space_id, documents=stored)
    return stored, changes
