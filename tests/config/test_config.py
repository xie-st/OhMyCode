"""Tests for four-layer configuration merging."""

import json
from pathlib import Path

from ohmycode.config.config import DEFAULT_CONFIG, OhMyCodeConfig, load_config, merge_configs


def test_default_config_has_required_keys():
    assert "provider" in DEFAULT_CONFIG
    assert "model" in DEFAULT_CONFIG
    assert "mode" in DEFAULT_CONFIG
    assert "max_turns" in DEFAULT_CONFIG
    assert "rules" in DEFAULT_CONFIG
    assert "context_enabled" in DEFAULT_CONFIG
    assert "context_visibility" in DEFAULT_CONFIG


def test_merge_scalar_override():
    base = {"provider": "anthropic", "model": "claude-3"}
    override = {"model": "gpt-4o"}
    result = merge_configs(base, override)
    assert result["provider"] == "anthropic"
    assert result["model"] == "gpt-4o"


def test_merge_array_concat():
    base = {"rules": [{"tool": "bash", "action": "deny"}]}
    override = {"rules": [{"tool": "edit", "action": "ask"}]}
    result = merge_configs(base, override)
    assert len(result["rules"]) == 2


def test_merge_deep_object():
    base = {"a": {"b": 1, "c": 2}}
    override = {"a": {"c": 3, "d": 4}}
    result = merge_configs(base, override)
    assert result["a"] == {"b": 1, "c": 3, "d": 4}


def test_load_config_defaults_only(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    config = load_config(cli_overrides={})
    assert config.provider == DEFAULT_CONFIG["provider"]
    assert config.mode == "default"


def test_load_config_user_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    user_dir = tmp_path / ".ohmycode"
    user_dir.mkdir()
    (user_dir / "config.json").write_text(json.dumps({"model": "gpt-4o-mini"}))
    config = load_config(cli_overrides={})
    assert config.model == "gpt-4o-mini"


def test_load_config_cli_wins(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    user_dir = tmp_path / ".ohmycode"
    user_dir.mkdir()
    (user_dir / "config.json").write_text(json.dumps({"model": "gpt-4o-mini"}))
    config = load_config(cli_overrides={"model": "claude-opus-4-6"})
    assert config.model == "claude-opus-4-6"


def test_ohmycode_config_validation():
    config = OhMyCodeConfig(**DEFAULT_CONFIG)
    assert config.max_turns == 100
    assert config.output_tokens_reserved == 8192
    assert config.context_enabled is True
    assert config.context_visibility == "silent"
