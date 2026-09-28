"""Typer CLI entrypoint for ArchbeeCLI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from archbee_cli import __version__
from archbee_cli.analysis.runner import ALL_ANALYSIS_TYPES, AnalysisRunner
from archbee_cli.archbee.client import ArchbeeClient
from archbee_cli.changes.apply import apply_finding
from archbee_cli.config import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_STORAGE_DIR,
    AppConfig,
    build_init_config,
    default_config_path,
    load_config,
    save_config,
)
from archbee_cli.documents.pull import pull_space
from archbee_cli.documents.store import DocumentStore
from archbee_cli.errors import ArchbeeCLIError
from archbee_cli.findings.models import FindingsStore, ReviewStatus
from archbee_cli.gemini.client import GeminiClient
from archbee_cli.logging_setup import setup_logging
from archbee_cli.review.interface import review_findings
from archbee_cli.style_guide.loader import load_style_guide

app = typer.Typer(
    name="ArchbeeCLI",
    help=(
        "Local CLI companion for analyzing Archbee documentation with Gemini "
        "against your Markdown style guide. Never modifies Archbee without "
        "explicit approval."
    ),
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, ArchbeeCLIError):
        err_console.print(f"[red]{exc.format()}[/red]")
        raise typer.Exit(code=1) from exc
    err_console.print(f"[red]Unexpected error: {exc}[/red]")
    raise typer.Exit(code=1) from exc


def _load(config_path: Path | None, log_level: str | None) -> AppConfig:
    config = load_config(config_path)
    setup_logging(log_level or config.log_level)  # type: ignore[arg-type]
    return config


def _storage(config: AppConfig) -> Path:
    path = Path(config.storage.directory)
    path.mkdir(parents=True, exist_ok=True)
    return path


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", help="Show version and exit.", is_eager=True
    ),
) -> None:
    if version:
        console.print(__version__)
        raise typer.Exit()


@app.command("init")
def init_cmd(
    space_id: Optional[str] = typer.Option(
        None, "--space-id", help="Archbee Space / docSpace ID."
    ),
    style_guide: Optional[str] = typer.Option(
        None, "--style-guide", help="Path to Markdown style guide."
    ),
    gemini_model: str = typer.Option(
        DEFAULT_GEMINI_MODEL, "--gemini-model", help="Gemini model id."
    ),
    storage: str = typer.Option(
        DEFAULT_STORAGE_DIR, "--storage", help="Local data directory."
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Do not prompt; require options/env."
    ),
) -> None:
    """Create local ArchbeeCLI configuration. Secrets stay in the environment."""
    try:
        import os

        resolved_space = space_id or os.environ.get("ARCHBEE_SPACE_ID") or ""
        resolved_style = style_guide or "./docs/Style-guide.txt"

        if not non_interactive:
            if not resolved_space:
                resolved_space = typer.prompt("Archbee Space ID")
            resolved_style = typer.prompt("Style guide path", default=resolved_style)
            gemini_model = typer.prompt("Gemini model", default=gemini_model)
            console.print(
                "\n[bold]Secrets[/bold] are read from environment variables "
                "(never written to config.toml):\n"
                "  ARCHBEE_API_KEY\n"
                "  GEMINI_API_KEY\n"
            )
            console.print(
                "[yellow]Note:[/yellow] Document content is sent to Gemini during analysis."
            )

        if not resolved_space:
            raise ArchbeeCLIError(
                "Space ID is required.",
                hint="Pass --space-id or set ARCHBEE_SPACE_ID.",
            )

        config = build_init_config(
            space_id=resolved_space,
            style_guide=resolved_style,
            gemini_model=gemini_model,
            storage_directory=storage,
        )
        path = save_config(config)
        # Ensure storage dirs exist.
        DocumentStore(Path(storage) if Path(storage).is_absolute() else Path.cwd() / storage)
        console.print(f"Wrote configuration to {path}")
        console.print("Set ARCHBEE_API_KEY and GEMINI_API_KEY before pull/analyze.")
    except Exception as exc:
        _handle_error(exc)


@app.command("pull")
def pull_cmd(
    space: Optional[str] = typer.Option(
        None, "--space", help="Override configured Space ID for this pull."
    ),
    force: bool = typer.Option(
        False, "--force", help="Force a full re-download of document content."
    ),
    config: Optional[Path] = typer.Option(None, "--config", help="Path to config.toml"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Retrieve documentation from Archbee into a local snapshot. Does not call Gemini."""
    try:
        level = "verbose" if verbose else "quiet" if quiet else None
        cfg = _load(config, level)
        if space:
            cfg.archbee.space_id = space
        space_id, api_key = cfg.require_archbee_credentials()
        store = DocumentStore(_storage(cfg))
        with ArchbeeClient(
            space_id=space_id,
            api_key=api_key,
            base_url=cfg.archbee.base_url,
        ) as client:
            docs, changes = pull_space(
                client=client, store=store, force=force, show_progress=not quiet
            )
        console.print(f"Retrieved {len(docs)} documents.")
        console.print(
            f"Added: {len(changes.added)}  "
            f"Updated: {len(changes.updated)}  "
            f"Removed: {len(changes.removed)}  "
            f"Unchanged: {len(changes.unchanged)}"
        )
    except Exception as exc:
        _handle_error(exc)


@app.command("analyze")
def analyze_cmd(
    types: Optional[str] = typer.Option(
        None,
        "--types",
        help=f"Comma-separated analysis types: {','.join(ALL_ANALYSIS_TYPES)}",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", help="Analyze only the first N local documents (debug)."
    ),
    config: Optional[Path] = typer.Option(None, "--config"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Run Gemini analysis against the local snapshot and style guide."""
    try:
        level = "verbose" if verbose else "quiet" if quiet else None
        cfg = _load(config, level)
        cfg.require_gemini_api_key()
        style_path = cfg.require_style_guide()
        # Touch style guide early for clearer errors.
        load_style_guide(style_path)

        analysis_types = (
            [part.strip() for part in types.split(",") if part.strip()]
            if types
            else list(ALL_ANALYSIS_TYPES)
        )
        unknown = [t for t in analysis_types if t not in ALL_ANALYSIS_TYPES]
        if unknown:
            raise ArchbeeCLIError(
                f"Unknown analysis type(s): {', '.join(unknown)}",
                hint=f"Choose from: {', '.join(ALL_ANALYSIS_TYPES)}",
            )

        storage = _storage(cfg)
        runner = AnalysisRunner(
            document_store=DocumentStore(storage),
            findings_store=FindingsStore(storage),
            gemini=GeminiClient(
                api_key=cfg.require_gemini_api_key(),
                model=cfg.gemini.model,
            ),
            style_guide_path=style_path,
        )
        result = runner.run(analysis_types=analysis_types, limit=limit)

        table = Table(title=f"Findings ({len(result.findings)})")
        table.add_column("ID")
        table.add_column("Type")
        table.add_column("Severity")
        table.add_column("Confidence")
        table.add_column("Document")
        table.add_column("Description")
        for finding in result.findings:
            table.add_row(
                finding.id,
                finding.type.value,
                finding.severity.value,
                finding.confidence.value,
                finding.document_title or finding.document_id or "",
                (finding.description[:80] + "…")
                if len(finding.description) > 80
                else finding.description,
            )
        console.print(table)
        if result.notes:
            console.print(f"\nNotes: {result.notes}")
        console.print("\nReview interactively with: ArchbeeCLI review")
    except Exception as exc:
        _handle_error(exc)


@app.command("review")
def review_cmd(
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Interactively review findings. Does not write to Archbee."""
    try:
        cfg = _load(config, None)
        storage = _storage(cfg)
        review_findings(
            FindingsStore(storage),
            documents_dir=storage / "documents",
        )
    except Exception as exc:
        _handle_error(exc)


@app.command("apply")
def apply_cmd(
    finding_id: str = typer.Option(..., "--finding", help="Finding ID to apply."),
    approve: bool = typer.Option(
        False,
        "--approve",
        help="Required explicit confirmation to write to Archbee.",
    ),
    config: Optional[Path] = typer.Option(None, "--config"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Apply an accepted finding's proposed change to Archbee (explicit approval required)."""
    try:
        cfg = _load(config, "verbose" if verbose else None)
        storage = _storage(cfg)
        findings_store = FindingsStore(storage)
        analysis = findings_store.load_latest()
        if analysis is None:
            raise ArchbeeCLIError("No analysis results found.", hint="Run analyze first.")
        finding = next((f for f in analysis.findings if f.id == finding_id), None)
        if finding is None:
            raise ArchbeeCLIError(f"Finding not found: {finding_id}")

        if not approve:
            raise ArchbeeCLIError(
                "Refusing to write to Archbee without --approve.",
                hint="Re-run with --approve after reviewing the proposed change.",
            )

        space_id, api_key = cfg.require_archbee_credentials()
        with ArchbeeClient(
            space_id=space_id,
            api_key=api_key,
            base_url=cfg.archbee.base_url,
        ) as client:
            updated = apply_finding(
                finding=finding,
                archbee=client,
                document_store=DocumentStore(storage),
                findings_store=findings_store,
                approved=True,
            )
        console.print(
            f"Applied finding {updated.id} to Archbee "
            f"(status={updated.status.value})."
        )
        console.print("Local snapshot refreshed for the updated document.")
    except Exception as exc:
        _handle_error(exc)


@app.command("show")
def show_cmd(
    finding_id: Optional[str] = typer.Argument(None, help="Finding ID (default: list)."),
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Show a finding or list latest findings."""
    try:
        cfg = _load(config, "quiet")
        store = FindingsStore(_storage(cfg))
        analysis = store.load_latest()
        if analysis is None:
            console.print("No findings stored yet.")
            raise typer.Exit()
        if finding_id is None:
            for finding in analysis.findings:
                console.print(
                    f"{finding.id}  {finding.status.value:9}  "
                    f"{finding.type.value}  {finding.document_title or ''}"
                )
            raise typer.Exit()
        finding = next((f for f in analysis.findings if f.id == finding_id), None)
        if finding is None:
            raise ArchbeeCLIError(f"Finding not found: {finding_id}")
        from archbee_cli.review.interface import render_finding

        render_finding(finding, index=1, total=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _handle_error(exc)


@app.command("status")
def status_cmd(
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Show local configuration and snapshot status (no secrets)."""
    try:
        path = config or default_config_path()
        if not path.is_file():
            console.print("Not initialized. Run `ArchbeeCLI init` first.")
            raise typer.Exit(code=1)
        cfg = _load(path, "quiet")
        storage = _storage(cfg)
        docs = DocumentStore(storage).list_documents()
        analysis = FindingsStore(storage).load_latest()
        console.print(f"Config: {path}")
        console.print(f"Space ID: {cfg.archbee.space_id or '(unset)'}")
        console.print(f"Gemini model: {cfg.gemini.model}")
        console.print(f"Style guide: {cfg.analysis.style_guide}")
        console.print(f"Storage: {storage}")
        console.print(f"Local documents: {len(docs)}")
        console.print(
            f"ARCHBEE_API_KEY set: {'yes' if cfg.archbee_api_key else 'no'}"
        )
        console.print(
            f"GEMINI_API_KEY set: {'yes' if cfg.gemini_api_key else 'no'}"
        )
        if analysis:
            pending = sum(1 for f in analysis.findings if f.status == ReviewStatus.PENDING)
            console.print(
                f"Latest analysis: {analysis.id} "
                f"({len(analysis.findings)} findings, {pending} pending)"
            )
        else:
            console.print("Latest analysis: (none)")
    except typer.Exit:
        raise
    except Exception as exc:
        _handle_error(exc)


if __name__ == "__main__":
    app()
