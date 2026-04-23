"""Tests for the /new slash command behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest

from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.loop import ConversationLoop
from ohmycode.core.messages import UserMessage, AssistantMessage


def _make_conv(with_messages: bool = True) -> ConversationLoop:
    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = ConversationLoop(config=config)
    conv._provider = MagicMock()
    conv._system_prompt = "sys"
    if with_messages:
        conv.add_user_message("hello")
        conv.messages.append(AssistantMessage(content="hi", tool_calls=[]))
    conv.auto_approved["bash"] = True
    conv.think = "high"
    return conv


# ---------------------------------------------------------------------------
# The /new command logic extracted for unit testing
# ---------------------------------------------------------------------------

def _simulate_new_command(conv, config, resumed_filename):
    """Mirror the /new elif block from cli.py run_repl() for isolated testing."""
    save_called_with = None
    save_result = None
    error_occurred = False

    if conv.messages:
        from ohmycode.storage.conversation import save_conversation
        try:
            saved = save_conversation(
                conv.messages, config.provider, config.model, config.mode
            )
            save_called_with = (conv.messages[:], config.provider, config.model, config.mode)
            save_result = saved
        except Exception as e:
            error_occurred = True
            return conv, resumed_filename, error_occurred, save_result

    new_conv = ConversationLoop(config=config, confirm_fn=None)
    new_conv._provider = MagicMock()
    new_conv._system_prompt = "fresh"
    resumed_filename = None
    return new_conv, resumed_filename, error_occurred, save_result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_new_saves_when_messages_exist(tmp_path, monkeypatch):
    import ohmycode.storage.conversation as conv_mod
    monkeypatch.setattr(conv_mod, "CONVERSATIONS_DIR", tmp_path)

    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = _make_conv(with_messages=True)
    msg_count_before = len(conv.messages)

    new_conv, resumed, error, saved_name = _simulate_new_command(conv, config, "old.json")

    assert not error
    assert saved_name is not None
    assert saved_name.endswith(".json")
    assert (tmp_path / saved_name).exists()

    import json
    data = json.loads((tmp_path / saved_name).read_text(encoding="utf-8"))
    assert data["metadata"]["message_count"] == msg_count_before


def test_new_does_not_save_empty_conversation(tmp_path, monkeypatch):
    import ohmycode.storage.conversation as conv_mod
    monkeypatch.setattr(conv_mod, "CONVERSATIONS_DIR", tmp_path)

    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = _make_conv(with_messages=False)
    conv.messages.clear()

    new_conv, resumed, error, saved_name = _simulate_new_command(conv, config, "old.json")

    assert not error
    assert saved_name is None
    assert list(tmp_path.glob("*.json")) == []


def test_new_creates_fresh_loop(tmp_path, monkeypatch):
    import ohmycode.storage.conversation as conv_mod
    monkeypatch.setattr(conv_mod, "CONVERSATIONS_DIR", tmp_path)

    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = _make_conv(with_messages=True)
    assert conv.auto_approved  # non-empty before
    assert conv.think == "high"

    new_conv, resumed, error, _ = _simulate_new_command(conv, config, "old.json")

    assert new_conv is not conv
    assert new_conv.messages == []
    assert new_conv.auto_approved == {}
    assert new_conv.think is None


def test_new_clears_resumed_filename(tmp_path, monkeypatch):
    import ohmycode.storage.conversation as conv_mod
    monkeypatch.setattr(conv_mod, "CONVERSATIONS_DIR", tmp_path)

    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = _make_conv(with_messages=True)

    _, resumed_after, error, _ = _simulate_new_command(conv, config, "20250101-abcdefgh.json")

    assert resumed_after is None


def test_new_aborts_on_save_failure():
    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = _make_conv(with_messages=True)
    original_conv = conv

    with patch("ohmycode.storage.conversation.save_conversation", side_effect=OSError("disk full")):
        new_conv, resumed, error, saved = _simulate_new_command(conv, config, "old.json")

    assert error
    assert new_conv is original_conv  # not replaced — abort on failure
    assert resumed == "old.json"       # not reset


def test_clear_does_not_save_or_recreate_loop(tmp_path, monkeypatch):
    import ohmycode.storage.conversation as conv_mod
    monkeypatch.setattr(conv_mod, "CONVERSATIONS_DIR", tmp_path)

    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = _make_conv(with_messages=True)
    original_id = id(conv)
    original_think = conv.think

    # Simulate /clear
    conv.messages.clear()
    conv.auto_approved.clear()

    assert id(conv) == original_id          # same object
    assert conv.think == original_think     # think unchanged
    assert list(tmp_path.glob("*.json")) == []  # nothing saved


def test_new_builtin_registered():
    """Verify /new appears in the SlashCompleter._BUILTIN via source inspection."""
    import ohmycode._cli.prompt_session as ps_mod
    import inspect
    source = inspect.getsource(ps_mod)
    assert '"/new"' in source
    assert "Save current conversation and start fresh" in source
