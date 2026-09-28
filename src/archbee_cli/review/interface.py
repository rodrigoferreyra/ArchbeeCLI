"""Interactive terminal review of findings. Never writes to Archbee by itself."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.text import Text

from archbee_cli.findings.models import (
    Finding,
    FindingsStore,
    ReviewStatus,
)

console = Console()


def _diff_text(before: str | None, after: str | None) -> str | None:
    if before is None and after is None:
        return None
    before = before or ""
    after = after or ""
    if before == after:
        return None
    lines = []
    for line in before.splitlines() or [""]:
        lines.append(f"- {line}")
    for line in after.splitlines() or [""]:
        lines.append(f"+ {line}")
    return "\n".join(lines)


def render_finding(finding: Finding, *, index: int, total: int) -> None:
    header = Text.assemble(
        ("Finding ", "bold"),
        (f"{index} of {total}", "bold cyan"),
        (f"  [{finding.status.value}]", "dim"),
    )
    console.print(header)
    console.print()
    console.print(Text("TYPE", style="bold"))
    console.print(finding.type.value)
    console.print()
    console.print(Text("SEVERITY / CONFIDENCE", style="bold"))
    console.print(f"{finding.severity.value} / {finding.confidence.value}")
    console.print()
    console.print(Text("DOCUMENT", style="bold"))
    console.print(finding.document_title or finding.document_id or "(none)")
    if finding.related_document_ids:
        console.print()
        console.print(Text("RELATED DOCUMENTS", style="bold"))
        console.print(", ".join(finding.related_document_ids))
    console.print()
    console.print(Text("DESCRIPTION", style="bold"))
    console.print(finding.description)
    if finding.style_guide_reference:
        console.print()
        console.print(Text("STYLE GUIDE", style="bold"))
        ref = finding.style_guide_reference
        if ref.section:
            console.print(f"Section: {ref.section}")
        if ref.rule:
            console.print(f"Rule: {ref.rule}")
    if finding.evidence:
        console.print()
        console.print(Text("EVIDENCE", style="bold"))
        for item in finding.evidence:
            loc = f" ({item.location})" if item.location else ""
            doc = ""
            if item.document_title or item.document_id:
                doc = f" [{item.document_title or item.document_id}]"
            console.print(Panel(f'"{item.text}"{loc}{doc}', expand=False))
    if finding.suggested_action:
        console.print()
        console.print(Text("SUGGESTED ACTION", style="bold"))
        console.print(finding.suggested_action)
    if finding.proposed_change:
        console.print()
        console.print(Text("PROPOSED CHANGE", style="bold"))
        diff = _diff_text(finding.proposed_change.before, finding.proposed_change.after)
        if diff:
            console.print(Syntax(diff, "diff", theme="ansi_dark", word_wrap=True))
        elif finding.proposed_change.description:
            console.print(finding.proposed_change.description)
    console.print()
    console.print(
        "[a] Accept  [r] Reject  [s] Skip  [o] Open path  [n] Next  [q] Quit"
    )


def review_findings(store: FindingsStore, *, documents_dir=None) -> None:
    analysis = store.load_latest()
    if analysis is None or not analysis.findings:
        console.print("No findings to review. Run `ArchbeeCLI analyze` first.")
        return

    findings = analysis.findings
    index = 0
    while 0 <= index < len(findings):
        finding = findings[index]
        console.clear()
        render_finding(finding, index=index + 1, total=len(findings))
        choice = Prompt.ask(
            "Action",
            choices=["a", "r", "s", "o", "n", "q"],
            default="n",
        ).lower()
        if choice == "q":
            break
        if choice == "a":
            store.update_finding_status(finding.id, ReviewStatus.ACCEPTED)
            finding.status = ReviewStatus.ACCEPTED
            console.print(
                "[green]Accepted locally.[/green] "
                "Use `ArchbeeCLI apply --finding <id>` to push an approved change."
            )
            Prompt.ask("Press Enter to continue", default="")
            index += 1
        elif choice == "r":
            store.update_finding_status(finding.id, ReviewStatus.REJECTED)
            finding.status = ReviewStatus.REJECTED
            index += 1
        elif choice == "s":
            store.update_finding_status(finding.id, ReviewStatus.SKIPPED)
            finding.status = ReviewStatus.SKIPPED
            index += 1
        elif choice == "o":
            if documents_dir and finding.document_id:
                path = documents_dir / f"{finding.document_id.replace('/', '_')}.md"
                console.print(f"Local snapshot path: {path}")
            else:
                console.print("No local document path available.")
            Prompt.ask("Press Enter to continue", default="")
        else:
            index += 1

    console.print("Review session ended.")
