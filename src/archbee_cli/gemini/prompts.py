"""Prompt builders for Gemini documentation analysis."""

from __future__ import annotations

from archbee_cli.documents.models import StoredDocument
from archbee_cli.style_guide.loader import StyleGuide

SYSTEM_INSTRUCTIONS = """\
You are a documentation analyst assisting a technical writer.

Your job is to find evidence-based issues in Archbee documentation.
You do NOT rewrite documentation autonomously and you do NOT invent problems.

Product principles:
- Evidence over confidence. Every finding needs concrete excerpts.
- Prefer "may" / "potential" language unless evidence is strong.
- The user's style guide is authoritative for style assessment.
- Do NOT invent style-guide rules. Style guide violations require a real rule/section.
- Distinguish style_guide_violation from general_documentation_quality.
- Do not flood the user with trivial stylistic nits.
- Never claim certainty without evidence.
- Never include API keys or credentials in output.
"""


def build_analysis_prompt(
    *,
    documents: list[StoredDocument],
    style_guide: StyleGuide,
    analysis_types: list[str],
    max_chars_per_doc: int = 8000,
) -> str:
    type_guidance = {
        "terminology": (
            "Identify potentially inconsistent terminology across documents. "
            "Do not assume variants are equivalent; explain why they may conflict."
        ),
        "duplicates": (
            "Identify documents/sections with substantial overlapping information. "
            "Suggest merge/link/remove/leave-unchanged options; do not pick a canonical page."
        ),
        "stale": (
            "Identify potentially stale or contradictory content. "
            "Prefer 'potentially_stale' over claiming confirmed obsolescence without strong evidence."
        ),
        "style": (
            "Evaluate documents against the supplied style guide only. "
            "Every style_guide_violation must cite style_guide_reference.section and/or rule."
        ),
    }

    requested = []
    for key in analysis_types:
        if key in type_guidance:
            requested.append(f"- {key}: {type_guidance[key]}")

    doc_blocks: list[str] = []
    for doc in documents:
        content = doc.content
        if len(content) > max_chars_per_doc:
            content = content[:max_chars_per_doc] + "\n\n[truncated]"
        doc_blocks.append(
            f"### Document\n"
            f"- id: {doc.id}\n"
            f"- title: {doc.title}\n"
            f"- url_key: {doc.url_key or ''}\n\n"
            f"{content}"
        )

    style_sections = "\n".join(
        f"- {section.heading}" for section in style_guide.sections[:80]
    )

    # Cap style guide size in the prompt while keeping original wording.
    style_body = style_guide.raw_markdown
    if len(style_body) > 20000:
        style_body = style_body[:20000] + "\n\n[style guide truncated]"

    return f"""\
Analyze the following Archbee documentation snapshot.

Analysis types requested:
{chr(10).join(requested) if requested else "- all MVP types"}

Return structured findings only. If nothing noteworthy is found, return an empty findings list.

## Style guide (authoritative)
Path: {style_guide.path}

Section headings:
{style_sections or "(no headings detected)"}

Full style guide Markdown:
{style_body}

## Documents
{chr(10).join(doc_blocks)}
"""
