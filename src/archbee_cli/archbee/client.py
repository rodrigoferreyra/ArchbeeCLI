"""Archbee Public API client.

Auth and endpoints verified against Archbee docs (api.archbee.com/api/public-api):

- Auth: Authorization: Bearer base64(docSpaceId~apiKey)
- List/search: POST /docs/search  (empty query + type=words returns all docs)
- Get document: GET /doc with JSON body {docId, format}
- Update/create: POST /doc with JSON body {docId?, content, format, title, ...}

Note: GET /doc unusually accepts a JSON body; httpx supports this via request().
"""

from __future__ import annotations

import base64
from typing import Any, Literal

import httpx

from archbee_cli.archbee.models import (
    ArchbeeDocSummary,
    ArchbeeDocumentContent,
    ArchbeeUpdateResult,
)
from archbee_cli.errors import ArchbeeAPIError
from archbee_cli.logging_setup import get_logger

logger = get_logger(__name__)

SearchType = Literal["words", "ai-chat", "ai-retrieval"]


def build_bearer_token(space_id: str, api_key: str) -> str:
    raw = f"{space_id}~{api_key}".encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


class ArchbeeClient:
    """Thin typed wrapper around the Archbee Public API."""

    def __init__(
        self,
        *,
        space_id: str,
        api_key: str,
        base_url: str = "https://api.archbee.com/api/public-api",
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.space_id = space_id
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": f"Bearer {build_bearer_token(space_id, api_key)}",
        }
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ArchbeeClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _raise_for_response(self, response: httpx.Response, *, action: str) -> None:
        status = response.status_code
        # Never include Authorization or body secrets in messages.
        detail = ""
        try:
            payload = response.json()
            messages = payload.get("messages")
            if isinstance(messages, list) and messages:
                detail = "; ".join(str(m) for m in messages)
            elif isinstance(payload.get("status"), str):
                detail = str(payload.get("status"))
        except Exception:
            detail = ""

        if status == 401:
            raise ArchbeeAPIError(
                f"Could not {action}.\n\nArchbee returned HTTP 401.",
                status_code=status,
                hint="Check ARCHBEE_API_KEY and archbee.space_id.",
            )
        if status == 403:
            raise ArchbeeAPIError(
                f"Could not {action}.\n\nArchbee returned HTTP 403.",
                status_code=status,
                hint="The API key may lack access to this Space.",
            )
        if status == 404:
            raise ArchbeeAPIError(
                f"Could not {action}.\n\nArchbee returned HTTP 404.",
                status_code=status,
                hint="Check the Space ID or document ID.",
            )
        if status == 429:
            raise ArchbeeAPIError(
                f"Could not {action}.\n\nArchbee rate-limited the request (HTTP 429).",
                status_code=status,
                hint="Wait and retry.",
            )
        if status >= 400:
            message = f"Could not {action}.\n\nArchbee returned HTTP {status}."
            if detail:
                message = f"{message}\n{detail}"
            raise ArchbeeAPIError(message, status_code=status)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        action: str,
    ) -> dict[str, Any]:
        logger.debug("%s %s", method, path)
        try:
            response = self._client.request(method, path, json=json_body)
        except httpx.TimeoutException as exc:
            raise ArchbeeAPIError(
                f"Could not {action}.\n\nThe request to Archbee timed out.",
                hint="Check network connectivity and retry.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ArchbeeAPIError(
                f"Could not {action}.\n\nNetwork error while contacting Archbee.",
                hint="Check network connectivity and retry.",
            ) from exc

        self._raise_for_response(response, action=action)
        try:
            payload = response.json()
        except Exception as exc:
            raise ArchbeeAPIError(
                f"Could not {action}.\n\nArchbee returned a non-JSON response.",
            ) from exc
        if not isinstance(payload, dict):
            raise ArchbeeAPIError(
                f"Could not {action}.\n\nUnexpected Archbee response shape.",
            )
        return payload

    def search_documents(
        self,
        query: str = "",
        *,
        search_type: SearchType = "words",
        parent_doc_id: str | None = None,
        doc_id: str | None = None,
        search_only_title: bool | None = None,
        data_text_format: Literal["markdown", "html"] | None = None,
    ) -> list[ArchbeeDocSummary]:
        body: dict[str, Any] = {"query": query, "type": search_type}
        if parent_doc_id is not None:
            body["parentDocId"] = parent_doc_id
        if doc_id is not None:
            body["docId"] = doc_id
        if search_only_title is not None:
            body["searchOnlyTitle"] = search_only_title
        if data_text_format is not None:
            body["dataTextFormat"] = data_text_format

        payload = self._request(
            "POST",
            "/docs/search",
            json_body=body,
            action="search documents",
        )
        data = payload.get("data") or {}
        docs = data.get("docs") or []
        if not isinstance(docs, list):
            raise ArchbeeAPIError(
                "Could not search documents.\n\nUnexpected docs payload from Archbee.",
            )
        return [ArchbeeDocSummary.model_validate(item) for item in docs]

    def list_all_documents(self) -> list[ArchbeeDocSummary]:
        """List every document in the Space.

        Per Archbee docs: word-based search with an empty query returns all docs.
        """
        logger.info("Listing documents in Space via search (empty query)")
        return self.search_documents(query="", search_type="words")

    def get_document(
        self,
        doc_id: str,
        *,
        fmt: Literal["markdown", "html", "json", "source"] = "markdown",
    ) -> ArchbeeDocumentContent:
        payload = self._request(
            "GET",
            "/doc",
            json_body={"docId": doc_id, "format": fmt},
            action=f"retrieve document {doc_id}",
        )
        # Successful responses are {content, format}; error envelopes use status.
        if payload.get("status") == "Not OK":
            messages = payload.get("messages") or ["Unknown error"]
            raise ArchbeeAPIError(
                f"Could not retrieve document {doc_id}.\n" + "; ".join(map(str, messages))
            )
        return ArchbeeDocumentContent.model_validate(payload)

    def update_document(
        self,
        *,
        doc_id: str,
        content: str,
        fmt: Literal["markdown", "mdx", "json"] = "markdown",
        title: str | None = None,
    ) -> ArchbeeUpdateResult:
        """Update an existing document. Call only after explicit user approval."""
        body: dict[str, Any] = {
            "docId": doc_id,
            "content": content,
            "format": fmt,
        }
        if title is not None:
            body["title"] = title
        payload = self._request(
            "POST",
            "/doc",
            json_body=body,
            action=f"update document {doc_id}",
        )
        if payload.get("status") not in (None, "OK"):
            messages = payload.get("messages") or [str(payload.get("status"))]
            raise ArchbeeAPIError(
                f"Could not update document {doc_id}.\n" + "; ".join(map(str, messages))
            )
        data = payload.get("data") or payload
        return ArchbeeUpdateResult.model_validate(data)
