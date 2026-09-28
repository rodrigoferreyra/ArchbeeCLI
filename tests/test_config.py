"""Configuration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from archbee_cli.config import (
    build_init_config,
    load_config,
    save_config,
)
from archbee_cli.errors import ConfigError


def test_save_and_load_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCHBEE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ARCHBEE_SPACE_ID", raising=False)

    config = build_init_config(
        space_id="space-123",
        style_guide="./style-guide.md",
        gemini_model="gemini-2.5-flash",
        storage_directory=str(tmp_path / ".ArchbeeCLI"),
    )
    path = tmp_path / ".ArchbeeCLI" / "config.toml"
    save_config(config, path)

    text = path.read_text(encoding="utf-8")
    assert "space-123" in text
    assert "api_key" not in text.lower()
    assert "secret" not in text

    monkeypatch.setenv("ARCHBEE_API_KEY", "arch-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-secret")
    loaded = load_config(path)
    assert loaded.archbee.space_id == "space-123"
    assert loaded.archbee_api_key == "arch-secret"
    assert loaded.gemini_api_key == "gem-secret"


def test_missing_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCHBEE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config = build_init_config(space_id="space", style_guide="./missing.md")
    path = tmp_path / "config.toml"
    save_config(config, path)
    loaded = load_config(path)
    with pytest.raises(ConfigError) as exc:
        loaded.require_archbee_credentials()
    assert "ARCHBEE_API_KEY" in (exc.value.hint or "")


def test_missing_style_guide(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCHBEE_API_KEY", raising=False)
    config = build_init_config(
        space_id="space",
        style_guide=str(tmp_path / "nope.md"),
    )
    with pytest.raises(ConfigError):
        config.require_style_guide()
