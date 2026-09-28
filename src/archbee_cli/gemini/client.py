"""Gemini client using the official google-genai SDK with structured output."""

from __future__ import annotations

from typing import Any

from archbee_cli.errors import GeminiAPIError
from archbee_cli.gemini.prompts import SYSTEM_INSTRUCTIONS, build_analysis_prompt
from archbee_cli.gemini.schemas import GeminiAnalysisResponse
from archbee_cli.logging_setup import get_logger

logger = get_logger(__name__)


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        if client is not None:
            self._client = client
        else:
            try:
                from google import genai
            except ImportError as exc:
                raise GeminiAPIError(
                    "The google-genai package is not installed.",
                    hint="Install project dependencies and retry.",
                ) from exc
            self._client = genai.Client(api_key=api_key)

    def analyze_documents(
        self,
        *,
        documents: list,
        style_guide,
        analysis_types: list[str],
    ) -> GeminiAnalysisResponse:
        prompt = build_analysis_prompt(
            documents=documents,
            style_guide=style_guide,
            analysis_types=analysis_types,
        )
        logger.info(
            "Sending %d documents to Gemini model=%s (document content is sent to Google)",
            len(documents),
            self.model,
        )
        try:
            from google.genai import types
        except ImportError:
            types = None  # type: ignore[assignment]

        try:
            config_kwargs: dict[str, Any] = {
                "response_mime_type": "application/json",
                "response_schema": GeminiAnalysisResponse,
                "system_instruction": SYSTEM_INSTRUCTIONS,
            }
            if types is not None:
                config = types.GenerateContentConfig(**config_kwargs)
            else:
                config = config_kwargs

            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except GeminiAPIError:
            raise
        except Exception as exc:
            # Never include request payloads that may contain secrets in the message.
            raise GeminiAPIError(
                "Gemini analysis failed.",
                hint="Check GEMINI_API_KEY, model name, and network connectivity.",
            ) from exc

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, GeminiAnalysisResponse):
            return parsed
        if parsed is not None:
            try:
                return GeminiAnalysisResponse.model_validate(parsed)
            except Exception as exc:
                raise GeminiAPIError(
                    "Gemini returned structured data that failed validation.",
                    hint=str(exc),
                ) from exc

        text = getattr(response, "text", None)
        if not text:
            raise GeminiAPIError(
                "Gemini returned an empty response.",
                hint="Retry the analysis or try a different model.",
            )
        try:
            return GeminiAnalysisResponse.model_validate_json(text)
        except Exception as exc:
            raise GeminiAPIError(
                "Gemini returned malformed structured output.",
                hint="The response could not be parsed into the expected findings schema.",
            ) from exc
