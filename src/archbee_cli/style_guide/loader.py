"""Markdown style guide loading. Content is preserved without rewriting."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from archbee_cli.errors import StyleGuideError


class StyleGuideSection(BaseModel):
    heading: str
    level: int
    content: str
    start_line: int


class StyleGuide(BaseModel):
    path: str
    raw_markdown: str
    sections: list[StyleGuideSection] = Field(default_factory=list)

    @property
    def rule_summaries(self) -> list[str]:
        """Lightweight list of section headings for prompts / findings."""
        return [section.heading for section in self.sections if section.heading]


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def load_style_guide(path: Path) -> StyleGuide:
    if not path.is_file():
        raise StyleGuideError(
            f"Style guide not found: {path}",
            hint="Provide a Markdown file path via analysis.style_guide.",
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StyleGuideError(
            f"Could not read style guide: {path}",
            hint=str(exc),
        ) from exc

    sections = _parse_sections(raw)
    # If the file has no ATX headings, keep a single synthetic section.
    if not sections and raw.strip():
        sections = [
            StyleGuideSection(
                heading="(entire style guide)",
                level=1,
                content=raw,
                start_line=1,
            )
        ]
    return StyleGuide(path=str(path), raw_markdown=raw, sections=sections)


def _parse_sections(markdown: str) -> list[StyleGuideSection]:
    lines = markdown.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            headings.append((index, level, title))

    sections: list[StyleGuideSection] = []
    for i, (start, level, title) in enumerate(headings):
        end = headings[i + 1][0] if i + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        sections.append(
            StyleGuideSection(
                heading=title,
                level=level,
                content=body,
                start_line=start + 1,
            )
        )
    return sections
