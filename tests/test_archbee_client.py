"""Archbee client tests using mocked HTTP responses."""

from __future__ import annotations

import base64

import httpx
import pytest

from archbee_cli.archbee.client import ArchbeeClient, build_bearer_token
from archbee_cli.errors import ArchbeeAPIError


def _auth_header(space: str, key: str) -> str:
    return f"Bearer {build_bearer_token(space, key)}"


def test_build_bearer_token() -> None:
    token = build_bearer_token("space1", "key1")
    decoded = base64.b64decode(token).decode("utf-8")
    assert decoded == "space1~key1"


def test_search_and_list(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.archbee.com/api/public-api/docs/search",
        json={
            "status": "OK",
            "data": {
                "docs": [
                    {
                        "id": "doc1",
                        "name": "Configure Voice",
                        "urlKey": "configure-voice",
                        "hidden": False,
                        "privacy": "public",
                    }
                ]
            },
        },
    )
    with ArchbeeClient(space_id="space", api_key="secret") as client:
        docs = client.list_all_documents()
    assert len(docs) == 1
    assert docs[0].id == "doc1"
    assert docs[0].name == "Configure Voice"
    request = httpx_mock.get_request()
    assert request.headers["Authorization"] == _auth_header("space", "secret")
    assert request.read()  # body consumed; ensure request existed


def test_get_document(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://api.archbee.com/api/public-api/doc",
        json={"content": "# Hello\n", "format": "markdown"},
    )
    with ArchbeeClient(space_id="space", api_key="secret") as client:
        doc = client.get_document("doc1")
    assert doc.content.startswith("# Hello")
    assert doc.format == "markdown"


def test_update_document(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.archbee.com/api/public-api/doc",
        json={"status": "OK", "data": {"docId": "doc1", "newRecord": False}},
    )
    with ArchbeeClient(space_id="space", api_key="secret") as client:
        result = client.update_document(doc_id="doc1", content="# Updated\n")
    assert result.doc_id == "doc1"
    assert result.new_record is False


def test_auth_error_is_actionable(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.archbee.com/api/public-api/docs/search",
        status_code=401,
        json={"status": "Not OK", "messages": ["Unauthorized"]},
    )
    with ArchbeeClient(space_id="space", api_key="bad") as client:
        with pytest.raises(ArchbeeAPIError) as exc:
            client.list_all_documents()
    assert "401" in str(exc.value)
    assert "ARCHBEE_API_KEY" in (exc.value.hint or "")
    assert "bad" not in str(exc.value)
    assert "bad" not in (exc.value.hint or "")


def test_network_error() -> None:
    transport = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("fail"))
    )
    with ArchbeeClient(space_id="space", api_key="secret", transport=transport) as client:
        with pytest.raises(ArchbeeAPIError) as exc:
            client.list_all_documents()
    assert "Network" in str(exc.value)
