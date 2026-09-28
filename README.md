# ArchbeeCLI

Local CLI companion for technical writers who maintain documentation in [Archbee](https://www.archbee.com/).

ArchbeeCLI:

1. Pulls a Space via the **Archbee Public API** into a local snapshot  
2. Loads your **Markdown style guide** as authoritative assessment guidance  
3. Analyzes documentation with **Gemini** (official `google-genai` SDK)  
4. Presents **evidence-based findings** for interactive human review  
5. Writes back to Archbee **only** after explicit approval (`apply --approve`)

It does **not** automatically modify documentation.

> Document content and your style guide are sent to Gemini during analysis.

## Requirements

- Python 3.12+
- Archbee Space ID + API key
- Gemini API key

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick start

```bash
export ARCHBEE_API_KEY="..."
export ARCHBEE_SPACE_ID="..."
export GEMINI_API_KEY="..."

ArchbeeCLI init --space-id "$ARCHBEE_SPACE_ID" --style-guide ./docs/Style-guide.txt
ArchbeeCLI pull
ArchbeeCLI analyze
ArchbeeCLI review
# After accepting a finding that includes a proposed change:
ArchbeeCLI apply --finding <id> --approve
```

## Commands

| Command | Purpose |
|---------|---------|
| `ArchbeeCLI init` | Create `.ArchbeeCLI/config.toml` (secrets stay in env vars) |
| `ArchbeeCLI pull` | Download Space docs into the local snapshot (no Gemini) |
| `ArchbeeCLI analyze` | Run Gemini analysis against snapshot + style guide |
| `ArchbeeCLI review` | Interactive terminal review (accept/reject/skip) |
| `ArchbeeCLI apply --finding ID --approve` | Push an accepted proposed change to Archbee |
| `ArchbeeCLI show [ID]` | List or display findings |
| `ArchbeeCLI status` | Show config/snapshot status without secrets |

Options:

```bash
ArchbeeCLI pull --space <space-id> --force
ArchbeeCLI analyze --types terminology,duplicates,stale,style --limit 10
ArchbeeCLI analyze -v
```

## Configuration

`.ArchbeeCLI/config.toml` (example):

```toml
[archbee]
space_id = "your-space-id"
base_url = "https://api.archbee.com/api/public-api"

[gemini]
model = "gemini-2.5-flash"

[analysis]
style_guide = "./docs/Style-guide.txt"

[storage]
directory = ".ArchbeeCLI"

log_level = "normal"
```

Environment variables (preferred for secrets):

```text
ARCHBEE_API_KEY
ARCHBEE_SPACE_ID
GEMINI_API_KEY
GEMINI_MODEL
ARCHBEE_CLI_STYLE_GUIDE
ARCHBEE_CLI_STORAGE
```

## Local data layout

```text
.ArchbeeCLI/
├── config.toml
├── documents/          # Markdown snapshots (keyed by Archbee doc ID)
├── analyses/           # Historical analysis JSON
├── findings/
│   └── latest.json
├── index.db            # SQLite index + FTS
└── metadata.json
```

## Archbee Public API notes

Verified against Archbee’s public API docs (`https://api.archbee.com/api/public-api`):

| Operation | Method | Path | Notes |
|-----------|--------|------|-------|
| Auth | — | — | `Authorization: Bearer base64(docSpaceId~apiKey)` |
| List / search | `POST` | `/docs/search` | Empty `query` + `type=words` returns all docs |
| Get document | `GET` | `/doc` | JSON **body** with `docId` + `format` (unusual for GET) |
| Update / create | `POST` | `/doc` | `docId` present → update; supports `markdown` / `mdx` / `json` |

MVP adaptations vs the SRS wording:

- There is no dedicated “list Space tree” endpoint; pull uses **search with an empty query**.
- Document GET uses a request body; the client uses `httpx` accordingly.
- Writes use Archbee’s update/create document endpoint after explicit `--approve`. Deletion is not implemented.

See also [docs/API.md](docs/API.md).

## Gemini

Uses the official [`google-genai`](https://googleapis.github.io/python-genai/) SDK with structured JSON output (`response_schema` + Pydantic).

The model id is configurable (`gemini.model` / `GEMINI_MODEL`). Default: `gemini-2.5-flash`.

Style-guide violations without a `style_guide_reference` are demoted to `general_documentation_quality` so the model’s personal preferences are not treated as style-guide rules.

## Safety

- Analysis never writes to Archbee.
- `apply` refuses without `--approve` and without an accepted finding.
- Rejected findings cannot be applied.
- API keys are not stored in `config.toml`, not sent to Gemini, and are redacted from logs.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Tests mock Archbee HTTP and Gemini; no live credentials are required.

## Project layout

```text
src/archbee_cli/
├── cli.py              # Typer presentation
├── config.py
├── archbee/            # Public API client
├── gemini/             # Official SDK + prompts + schemas
├── documents/          # Local snapshot + pull
├── style_guide/        # Markdown loader
├── analysis/           # Orchestration (no CLI coupling)
├── findings/           # Typed findings + persistence
├── review/             # Interactive Rich UI
└── changes/            # Explicit-approval writes
```
