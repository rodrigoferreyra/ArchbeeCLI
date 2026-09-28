"""Logging helpers that avoid leaking secrets or full document bodies."""

from __future__ import annotations

import logging
import re
from typing import Literal

from rich.console import Console
from rich.logging import RichHandler

LogLevel = Literal["quiet", "normal", "verbose"]

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)Bearer\s+[A-Za-z0-9+/=._~-]+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(api[_-]?key|authorization)\s*[=:]\s*\S+"), r"\1=[REDACTED]"),
]

console = Console(stderr=True)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern, replacement in _SECRET_PATTERNS:
            message = pattern.sub(replacement, message)
        record.msg = message
        record.args = ()
        return True


def setup_logging(level: LogLevel = "normal") -> None:
    root = logging.getLogger()
    root.handlers.clear()

    if level == "quiet":
        logging_level = logging.WARNING
    elif level == "verbose":
        logging_level = logging.DEBUG
    else:
        logging_level = logging.INFO

    handler = RichHandler(
        console=console,
        show_time=False,
        show_path=False,
        rich_tracebacks=False,
        markup=False,
    )
    handler.addFilter(RedactingFilter())
    logging.basicConfig(level=logging_level, format="%(message)s", handlers=[handler])


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
