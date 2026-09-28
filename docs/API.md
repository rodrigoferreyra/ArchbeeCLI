# Archbee & Gemini API notes (MVP)

This document records how ArchbeeCLI maps to the live APIs, so the implementation does not invent endpoints.

## Archbee Public API

Base URL: `https://api.archbee.com/api/public-api`

### Authentication

```http
Authorization: Bearer {base64(docSpaceId~apiKey)}
```

Team keys beginning with `abteam_` may access all spaces in an organization (per Archbee docs). ArchbeeCLI still requires a configured `space_id` for local snapshot provenance.

### Endpoints used

#### Search / list documents — `POST /docs/search`

Body (list all):

```json
{ "query": "", "type": "words" }
```

Optional fields used by the client when needed:

- `docId` — single document metadata
- `parentDocId` — children of a parent (`"null"` for roots, per docs)
- `dataTextFormat` — `markdown` | `html` (not relied on for full content in MVP)
- `searchOnlyTitle`

Response shape (simplified):

```json
{
  "status": "OK",
  "data": {
    "searchSessionId": "...",
    "docs": [
      {
        "id": "...",
        "name": "...",
        "urlKey": "...",
        "urlAlias": "...",
        "hidden": false,
        "privacy": "public",
        "highlight": {}
      }
    ]
  }
}
```

**MVP adaptation:** Pull uses empty-query word search as the Space inventory. There is no separate “export Space” endpoint in the public docs consulted for this MVP.

#### Get document — `GET /doc`

Request body (yes, body on GET):

```json
{ "docId": "...", "format": "markdown" }
```

`format`: `markdown` | `html` | `json` | `source`

Response:

```json
{ "content": "...", "format": "markdown" }
```

#### Update / create document — `POST /doc`

```json
{
  "docId": "...",
  "content": "...",
  "format": "markdown",
  "title": "optional"
}
```

`format`: `markdown` | `mdx` | `json`

Response:

```json
{
  "status": "OK",
  "data": { "docId": "...", "newRecord": false }
}
```

**Not implemented in MVP:** delete document, publish/update Space metadata, OpenAPI sync.

## Gemini

SDK: official `google-genai` (`from google import genai`).

Structured output via `GenerateContentConfig`:

- `response_mime_type="application/json"`
- `response_schema=<Pydantic model>`

Findings are validated into `GeminiAnalysisResponse` before entering the app. Malformed output raises a controlled `GeminiAPIError`.

Default model config value: `gemini-2.5-flash` (overridable; not hard-coded in call sites beyond that default).
