"""Gemini structured output handling tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from archbee_cli.analysis.runner import convert_gemini_response
from archbee_cli.errors import GeminiAPIError
from archbee_cli.findings.models import FindingType
from archbee_cli.gemini.client import GeminiClient
from archbee_cli.gemini.schemas import GeminiAnalysisResponse, GeminiFinding
from archbee_cli.style_guide.loader import StyleGuide


class FakeModels:
    def __init__(self, response):
        self._response = response

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        return self._response


class FakeClient:
    def __init__(self, response):
        self.models = FakeModels(response)


def test_valid_structured_response() -> None:
    parsed = GeminiAnalysisResponse(
        findings=[
            GeminiFinding(
                type="style_guide_violation",
                severity="medium",
                confidence="high",
                document_id="abc",
                document_title="Configure Voice",
                description="Heading uses title case",
                evidence=[],
                style_guide_reference={"section": "Headings", "rule": "sentence case"},
            )
        ]
    )
    client = GeminiClient(
        api_key="unused",
        model="gemini-2.5-flash",
        client=FakeClient(SimpleNamespace(parsed=parsed, text=None)),
    )
    result = client.analyze_documents(
        documents=[],
        style_guide=StyleGuide(path="x", raw_markdown="# Headings\n"),
        analysis_types=["style"],
    )
    assert len(result.findings) == 1
    assert result.findings[0].type == "style_guide_violation"


def test_malformed_json_response() -> None:
    client = GeminiClient(
        api_key="unused",
        model="gemini-2.5-flash",
        client=FakeClient(SimpleNamespace(parsed=None, text="{not-json")),
    )
    with pytest.raises(GeminiAPIError):
        client.analyze_documents(
            documents=[],
            style_guide=StyleGuide(path="x", raw_markdown="# X\n"),
            analysis_types=["style"],
        )


def test_empty_response() -> None:
    client = GeminiClient(
        api_key="unused",
        model="gemini-2.5-flash",
        client=FakeClient(SimpleNamespace(parsed=None, text=None)),
    )
    with pytest.raises(GeminiAPIError):
        client.analyze_documents(
            documents=[],
            style_guide=StyleGuide(path="x", raw_markdown="# X\n"),
            analysis_types=["style"],
        )


def test_style_finding_without_reference_is_demoted() -> None:
    raw = GeminiAnalysisResponse(
        findings=[
            GeminiFinding(
                type="style_guide_violation",
                description="I prefer shorter sentences",
                evidence=[],
                style_guide_reference=None,
            )
        ]
    )
    result = convert_gemini_response(
        raw, analysis_types=["style"], document_count=1, model="m"
    )
    assert result.findings[0].type == FindingType.QUALITY


def test_unexpected_type_coercion() -> None:
    raw = GeminiAnalysisResponse(
        findings=[
            GeminiFinding(
                type="general_documentation_quality",
                description="Missing intro context",
                evidence=[{"text": "starts abruptly", "location": None}],
            )
        ]
    )
    result = convert_gemini_response(
        raw, analysis_types=["style"], document_count=1, model="m"
    )
    assert result.findings[0].type == FindingType.QUALITY
    assert result.findings[0].evidence[0].text == "starts abruptly"
