"""Archbee Public API response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ArchbeeDocSummary(BaseModel):
    id: str
    name: str = ""
    url_key: str | None = Field(default=None, alias="urlKey")
    url_alias: str | None = Field(default=None, alias="urlAlias")
    hidden: bool = False
    privacy: str | None = None
    highlight: dict | list | str | None = None

    model_config = {"populate_by_name": True}


class ArchbeeDocumentContent(BaseModel):
    content: str = ""
    format: str = "markdown"


class ArchbeeUpdateResult(BaseModel):
    doc_id: str = Field(alias="docId")
    new_record: bool = Field(default=False, alias="newRecord")

    model_config = {"populate_by_name": True}
