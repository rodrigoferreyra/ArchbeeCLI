"""Application-level errors with actionable messages and no secret leakage."""

from __future__ import annotations


class ArchbeeCLIError(Exception):
    """Base error for user-facing CLI failures."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        self.message = message
        self.hint = hint
        super().__init__(message)

    def format(self) -> str:
        if self.hint:
            return f"{self.message}\n\n{self.hint}"
        return self.message


class ConfigError(ArchbeeCLIError):
    """Invalid or incomplete configuration."""


class ArchbeeAPIError(ArchbeeCLIError):
    """Archbee Public API failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        hint: str | None = None,
    ) -> None:
        self.status_code = status_code
        super().__init__(message, hint=hint)


class GeminiAPIError(ArchbeeCLIError):
    """Gemini API / structured-output failure."""


class StyleGuideError(ArchbeeCLIError):
    """Style guide loading failure."""


class StoreError(ArchbeeCLIError):
    """Local snapshot / findings store failure."""


class ApprovalRequiredError(ArchbeeCLIError):
    """Raised when a write is attempted without explicit approval."""
