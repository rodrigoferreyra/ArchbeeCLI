"""Local document models."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StoredDocument(BaseModel):
    id: str
    title: str = ""
    content: str = ""
    format: str = "markdown"
    url_key: str | None = None
    url_alias: str | None = None
    hidden: bool = False
    privacy: str | None = None
    space_id: str = ""
    content_hash: str = ""
    retrieved_at: datetime = Field(default_factory=utc_now)
    snapshot_id: str = ""


class PullChangeSummary(BaseModel):
    added: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)

    @property
    def total_retrieved(self) -> int:
        return (
            len(self.added)
            + len(self.updated)
            + len(self.unchanged)
        )
