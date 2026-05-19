"""Window B model selection fallback behavior.

The B model must fall back to the main config.model when window_b_model is
unset (empty string). Hardcoding gpt-4o-mini for provider=='openai' broke
DeepSeek/Moonshot/etc., all of which use the openai-compatible protocol
family with a different base_url. The fix: explicit window_b_model wins,
otherwise mirror config.model.
"""

from __future__ import annotations

from desktop.server.session import _pick_b_model
from ohmycode.config.config import OhMyCodeConfig


def test_pick_b_model_uses_window_b_model_when_set():
    config = OhMyCodeConfig(
        provider="openai",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-fake",
        window_b_model="deepseek-v4-flash",
    )
    assert _pick_b_model(config) == "deepseek-v4-flash"


def test_pick_b_model_falls_back_to_main_model_when_unset():
    """The critical regression: provider='openai' must NOT yank gpt-4o-mini."""
    config = OhMyCodeConfig(
        provider="openai",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-fake",
        # window_b_model defaults to ""
    )
    assert _pick_b_model(config) == "deepseek-v4-pro"


def test_pick_b_model_falls_back_for_anthropic_provider_too():
    config = OhMyCodeConfig(
        provider="anthropic",
        model="claude-opus-4-7",
        api_key="sk-ant-fake",
    )
    assert _pick_b_model(config) == "claude-opus-4-7"


def test_pick_b_model_window_b_overrides_for_anthropic_too():
    config = OhMyCodeConfig(
        provider="anthropic",
        model="claude-opus-4-7",
        api_key="sk-ant-fake",
        window_b_model="claude-haiku-4-5-20251001",
    )
    assert _pick_b_model(config) == "claude-haiku-4-5-20251001"
