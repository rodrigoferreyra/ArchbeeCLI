"""Configuration loading, validation, and interactive init."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, Field, field_validator

from archbee_cli.errors import ConfigError

DEFAULT_STORAGE_DIR = ".ArchbeeCLI"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
CONFIG_FILENAME = "config.toml"

LogLevel = Literal["quiet", "normal", "verbose"]


class ArchbeeConfig(BaseModel):
    space_id: str = ""
    base_url: str = "https://api.archbee.com/api/public-api"


class GeminiConfig(BaseModel):
    model: str = DEFAULT_GEMINI_MODEL


class AnalysisConfig(BaseModel):
    style_guide: str = "./style-guide.md"


class StorageConfig(BaseModel):
    directory: str = DEFAULT_STORAGE_DIR


class AppConfig(BaseModel):
    archbee: ArchbeeConfig = Field(default_factory=ArchbeeConfig)
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    log_level: LogLevel = "normal"

    # Secrets are never persisted in the TOML file by default.
    archbee_api_key: str | None = Field(default=None, exclude=True)
    gemini_api_key: str | None = Field(default=None, exclude=True)

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: Any) -> str:
        if value is None:
            return "normal"
        return str(value).lower()

    @property
    def storage_path(self) -> Path:
        return Path(self.storage.directory).expanduser().resolve()

    @property
    def style_guide_path(self) -> Path:
        return Path(self.analysis.style_guide).expanduser().resolve()

    def require_archbee_credentials(self) -> tuple[str, str]:
        space_id = self.archbee.space_id.strip()
        api_key = (self.archbee_api_key or "").strip()
        if not space_id:
            raise ConfigError(
                "Archbee Space ID is not configured.",
                hint="Set archbee.space_id in config.toml or ARCHBEE_SPACE_ID.",
            )
        if not api_key:
            raise ConfigError(
                "Archbee API key is not configured.",
                hint="Set ARCHBEE_API_KEY in the environment.",
            )
        return space_id, api_key

    def require_gemini_api_key(self) -> str:
        api_key = (self.gemini_api_key or "").strip()
        if not api_key:
            raise ConfigError(
                "Gemini API key is not configured.",
                hint="Set GEMINI_API_KEY in the environment.",
            )
        return api_key

    def require_style_guide(self) -> Path:
        path = self.style_guide_path
        if not path.is_file():
            raise ConfigError(
                f"Style guide not found: {path}",
                hint="Set analysis.style_guide to an existing Markdown file.",
            )
        return path


def find_project_root(start: Path | None = None) -> Path:
    """Walk upward looking for an existing .ArchbeeCLI directory or config."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        storage = candidate / DEFAULT_STORAGE_DIR
        if (storage / CONFIG_FILENAME).is_file() or storage.is_dir():
            return candidate
    return current


def default_config_path(project_root: Path | None = None) -> Path:
    root = project_root or find_project_root()
    return root / DEFAULT_STORAGE_DIR / CONFIG_FILENAME


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"Malformed configuration file: {path}",
            hint=str(exc),
        ) from exc


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or default_config_path()
    data: dict[str, Any] = {}
    if path.is_file():
        data = _read_toml(path)

    config = AppConfig.model_validate(data)

    # Environment variables always win for secrets and may override IDs.
    env_space = os.environ.get("ARCHBEE_SPACE_ID")
    if env_space:
        config.archbee.space_id = env_space

    config.archbee_api_key = os.environ.get("ARCHBEE_API_KEY") or config.archbee_api_key
    config.gemini_api_key = os.environ.get("GEMINI_API_KEY") or config.gemini_api_key

    env_model = os.environ.get("GEMINI_MODEL")
    if env_model:
        config.gemini.model = env_model

    env_style = os.environ.get("ARCHBEE_CLI_STYLE_GUIDE")
    if env_style:
        config.analysis.style_guide = env_style

    env_storage = os.environ.get("ARCHBEE_CLI_STORAGE")
    if env_storage:
        config.storage.directory = env_storage

    # Resolve relative storage against the config file's project root when possible.
    if not Path(config.storage.directory).is_absolute():
        root = path.parent.parent if path.name == CONFIG_FILENAME else Path.cwd()
        # config lives in <root>/.ArchbeeCLI/config.toml → parent.parent is root
        if path.parent.name == DEFAULT_STORAGE_DIR:
            config.storage.directory = str((path.parent.parent / config.storage.directory).resolve())
        else:
            config.storage.directory = str((root / config.storage.directory).resolve())

    return config


def save_config(config: AppConfig, config_path: Path | None = None) -> Path:
    path = config_path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "archbee": {
            "space_id": config.archbee.space_id,
            "base_url": config.archbee.base_url,
        },
        "gemini": {
            "model": config.gemini.model,
        },
        "analysis": {
            "style_guide": config.analysis.style_guide,
        },
        "storage": {
            # Persist a relative default when possible.
            "directory": DEFAULT_STORAGE_DIR,
        },
        "log_level": config.log_level,
    }
    with path.open("wb") as handle:
        tomli_w.dump(payload, handle)
    return path


def build_init_config(
    *,
    space_id: str,
    style_guide: str,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    storage_directory: str = DEFAULT_STORAGE_DIR,
    base_url: str = "https://api.archbee.com/api/public-api",
    log_level: LogLevel = "normal",
) -> AppConfig:
    return AppConfig(
        archbee=ArchbeeConfig(space_id=space_id, base_url=base_url),
        gemini=GeminiConfig(model=gemini_model),
        analysis=AnalysisConfig(style_guide=style_guide),
        storage=StorageConfig(directory=storage_directory),
        log_level=log_level,
    )
