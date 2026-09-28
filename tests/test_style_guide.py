"""Style guide loader tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from archbee_cli.errors import StyleGuideError
from archbee_cli.style_guide.loader import load_style_guide


def test_load_markdown_preserves_sections(tmp_path: Path) -> None:
    path = tmp_path / "style.md"
    path.write_text(
        "# Voice\n\nUse active voice.\n\n## Headings\n\nUse sentence case.\n",
        encoding="utf-8",
    )
    guide = load_style_guide(path)
    assert "Use active voice" in guide.raw_markdown
    assert [s.heading for s in guide.sections] == ["Voice", "Headings"]
    assert "sentence case" in guide.sections[1].content
    # Must not rewrite / normalize away original text.
    assert guide.raw_markdown == path.read_text(encoding="utf-8")


def test_plain_text_without_headings(tmp_path: Path) -> None:
    path = tmp_path / "Style-guide.txt"
    path.write_text("Prefer concise sentences.\nAvoid jargon.\n", encoding="utf-8")
    guide = load_style_guide(path)
    assert len(guide.sections) == 1
    assert "Prefer concise" in guide.sections[0].content


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(StyleGuideError):
        load_style_guide(tmp_path / "absent.md")
