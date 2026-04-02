"""Four-layer configuration: defaults < user < project < CLI overrides."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "openai",
    "model": "gpt-4o",
    "mode": "default",
    "max_turns": 100,
    "token_budget": 200000,
    "output_tokens_reserved": 8192,
    "rules": [],
    "system_prompt_append": "",
    "search_api": "",
    "search_api_key": "",
    "azure_endpoint": "",
    "azure_api_version": "2024-02-01",
    "base_url": "",
    "api_key": "",
    "auth_token": "",
}


class OhMyCodeConfig(BaseModel):
    """Validated configuration object."""

    provider: str = "openai"
    model: str = "gpt-4o"
    mode: str = "default"
    max_turns: int = 100
    token_budget: int = 200000
    output_tokens_reserved: int = 8192
    rules: list[dict[str, Any]] = Field(default_factory=list)
    system_prompt_append: str = ""
    search_api: str = ""
    search_api_key: str = ""
    azure_endpoint: str = ""
    azure_api_version: str = "2024-02-01"
    base_url: str = ""
    api_key: str = ""
    auth_token: str = ""


def merge_configs(base: dict, override: dict) -> dict:
    """Merge two config dicts: scalars override, lists concatenate, dicts merge deeply."""
    result = dict(base)
    for key, value in override.items():
        if key not in result:
            result[key] = value
        elif isinstance(value, list) and isinstance(result[key], list):
            result[key] = result[key] + value
        elif isinstance(value, dict) and isinstance(result[key], dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def _read_json(path: Path) -> dict:
    """Read a JSON config file; return an empty dict if missing or invalid."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_config(cli_overrides: dict[str, Any]) -> OhMyCodeConfig:
    """Load configuration from four layers: defaults < user < project < CLI."""
    home = Path(os.environ.get("HOME", Path.home()))
    user_config = _read_json(home / ".ohmycode" / "config.json")
    project_config = _read_json(Path.cwd() / ".ohmycode" / "config.json")

    cli_clean = {k: v for k, v in cli_overrides.items() if v is not None}

    merged = DEFAULT_CONFIG.copy()
    merged = merge_configs(merged, user_config)
    merged = merge_configs(merged, project_config)
    merged = merge_configs(merged, cli_clean)

    return OhMyCodeConfig(**merged)
