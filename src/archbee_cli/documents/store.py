"""SQLite index + filesystem snapshot for Archbee documents."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from archbee_cli.documents.models import PullChangeSummary, StoredDocument
from archbee_cli.errors import StoreError
from archbee_cli.logging_setup import get_logger

logger = get_logger(__name__)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class DocumentStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.documents_dir = root / "documents"
        self.analyses_dir = root / "analyses"
        self.findings_dir = root / "findings"
        self.db_path = root / "index.db"
        self.metadata_path = root / "metadata.json"
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        for path in (self.documents_dir, self.analyses_dir, self.findings_dir):
            path.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    format TEXT NOT NULL,
                    url_key TEXT,
                    url_alias TEXT,
                    hidden INTEGER NOT NULL DEFAULT 0,
                    privacy TEXT,
                    space_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    path TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    space_id TEXT NOT NULL,
                    document_count INTEGER NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                USING fts5(id UNINDEXED, title, content);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _doc_path(self, doc_id: str) -> Path:
        safe = doc_id.replace("/", "_")
        return self.documents_dir / f"{safe}.md"

    def list_documents(self) -> list[StoredDocument]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY title").fetchall()
        docs: list[StoredDocument] = []
        for row in rows:
            path = Path(row["path"])
            content = path.read_text(encoding="utf-8") if path.is_file() else ""
            docs.append(
                StoredDocument(
                    id=row["id"],
                    title=row["title"],
                    content=content,
                    format=row["format"],
                    url_key=row["url_key"],
                    url_alias=row["url_alias"],
                    hidden=bool(row["hidden"]),
                    privacy=row["privacy"],
                    space_id=row["space_id"],
                    content_hash=row["content_hash"],
                    retrieved_at=datetime.fromisoformat(row["retrieved_at"]),
                    snapshot_id=row["snapshot_id"],
                )
            )
        return docs

    def get_document(self, doc_id: str) -> StoredDocument | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
        if row is None:
            return None
        path = Path(row["path"])
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        return StoredDocument(
            id=row["id"],
            title=row["title"],
            content=content,
            format=row["format"],
            url_key=row["url_key"],
            url_alias=row["url_alias"],
            hidden=bool(row["hidden"]),
            privacy=row["privacy"],
            space_id=row["space_id"],
            content_hash=row["content_hash"],
            retrieved_at=datetime.fromisoformat(row["retrieved_at"]),
            snapshot_id=row["snapshot_id"],
        )

    def search(self, query: str, *, limit: int = 20) -> list[StoredDocument]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.* FROM documents_fts f
                JOIN documents d ON d.id = f.id
                WHERE documents_fts MATCH ?
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        results: list[StoredDocument] = []
        for row in rows:
            doc = self.get_document(row["id"])
            if doc:
                results.append(doc)
        return results

    def replace_snapshot(
        self,
        *,
        space_id: str,
        documents: list[StoredDocument],
    ) -> PullChangeSummary:
        snapshot_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()

        previous = {doc.id: doc for doc in self.list_documents()}
        incoming_ids = {doc.id for doc in documents}

        summary = PullChangeSummary()
        for doc in documents:
            digest = content_hash(doc.content)
            doc.content_hash = digest
            doc.snapshot_id = snapshot_id
            doc.space_id = space_id
            if doc.id not in previous:
                summary.added.append(doc.id)
            elif previous[doc.id].content_hash != digest:
                summary.updated.append(doc.id)
            else:
                summary.unchanged.append(doc.id)

        for old_id in previous:
            if old_id not in incoming_ids:
                summary.removed.append(old_id)

        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM documents_fts")
                conn.execute("DELETE FROM documents")
                for doc in documents:
                    path = self._doc_path(doc.id)
                    path.write_text(doc.content, encoding="utf-8")
                    conn.execute(
                        """
                        INSERT INTO documents (
                            id, title, format, url_key, url_alias, hidden, privacy,
                            space_id, content_hash, retrieved_at, snapshot_id, path
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            doc.id,
                            doc.title,
                            doc.format,
                            doc.url_key,
                            doc.url_alias,
                            int(doc.hidden),
                            doc.privacy,
                            space_id,
                            doc.content_hash,
                            doc.retrieved_at.isoformat(),
                            snapshot_id,
                            str(path),
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO documents_fts (id, title, content)
                        VALUES (?, ?, ?)
                        """,
                        (doc.id, doc.title, doc.content),
                    )
                conn.execute(
                    """
                    INSERT INTO snapshots (id, created_at, space_id, document_count)
                    VALUES (?, ?, ?, ?)
                    """,
                    (snapshot_id, now, space_id, len(documents)),
                )

            # Remove files for deleted docs
            for removed_id in summary.removed:
                path = self._doc_path(removed_id)
                if path.exists():
                    path.unlink()

            metadata = {
                "space_id": space_id,
                "snapshot_id": snapshot_id,
                "updated_at": now,
                "document_count": len(documents),
                "changes": summary.model_dump(),
            }
            self.metadata_path.write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            raise StoreError(
                "Failed to write local document snapshot.",
                hint=str(exc),
            ) from exc

        logger.info(
            "Snapshot %s stored: %d docs (%d added, %d updated, %d removed, %d unchanged)",
            snapshot_id,
            len(documents),
            len(summary.added),
            len(summary.updated),
            len(summary.removed),
            len(summary.unchanged),
        )
        return summary
