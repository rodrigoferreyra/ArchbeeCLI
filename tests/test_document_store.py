"""Document store / pull change summary tests."""

from __future__ import annotations

from pathlib import Path

from archbee_cli.documents.models import StoredDocument
from archbee_cli.documents.store import DocumentStore


def test_snapshot_change_detection(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path)
    first = [
        StoredDocument(id="a", title="A", content="one", space_id="s"),
        StoredDocument(id="b", title="B", content="two", space_id="s"),
    ]
    summary = store.replace_snapshot(space_id="s", documents=first)
    assert set(summary.added) == {"a", "b"}

    second = [
        StoredDocument(id="a", title="A", content="one", space_id="s"),
        StoredDocument(id="b", title="B", content="TWO", space_id="s"),
        StoredDocument(id="c", title="C", content="three", space_id="s"),
    ]
    summary2 = store.replace_snapshot(space_id="s", documents=second)
    assert summary2.unchanged == ["a"]
    assert summary2.updated == ["b"]
    assert summary2.added == ["c"]

    third = [StoredDocument(id="a", title="A", content="one", space_id="s")]
    summary3 = store.replace_snapshot(space_id="s", documents=third)
    assert set(summary3.removed) == {"b", "c"}
    assert store.get_document("a") is not None
    assert store.get_document("b") is None
