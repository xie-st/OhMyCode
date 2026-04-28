from __future__ import annotations

from unittest.mock import Mock

import pytest

from ohmycode._cli.repl_commands import handle_slash_command
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.context.packet import ContextPacket
from ohmycode.context.runtime import ContextRuntime
from ohmycode.context.store import ContextStore
from ohmycode.core.loop import ConversationLoop


def _runtime(tmp_path) -> ContextRuntime:
    return ContextRuntime(ContextStore(tmp_path / "context.db"))


def _conv() -> ConversationLoop:
    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = ConversationLoop(config=config)
    conv._system_prompt = "base"
    return conv


@pytest.mark.asyncio
async def test_context_command_shows_active_packet(tmp_path):
    runtime = _runtime(tmp_path)
    topic_id = runtime.store.create_topic("agent runtime", summary="one window")
    runtime.store.set_state("active_topic_id", topic_id)
    runtime.store.save_packet(
        ContextPacket(topic_id=topic_id, title="agent runtime", summary="one window", version=3)
    )
    prints = []

    await handle_slash_command(
        cmd="/context",
        parts=["/context"],
        raw_input="/context",
        conv=_conv(),
        config=OhMyCodeConfig(),
        config_overrides={},
        skills={},
        resumed_filename=None,
        repl_print=lambda *args, **kwargs: prints.append(" ".join(str(a) for a in args)),
        context_runtime=runtime,
    )

    output = "\n".join(prints)
    assert "agent runtime" in output
    assert "version" in output.lower()
    assert "one window" in output


@pytest.mark.asyncio
async def test_context_switch_records_correction_event(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.store.create_topic("first", summary="old")
    second = runtime.store.create_topic("second", summary="new")
    prints = []

    await handle_slash_command(
        cmd="/context",
        parts=["/context", f"switch {second}"],
        raw_input=f"/context switch {second}",
        conv=_conv(),
        config=OhMyCodeConfig(),
        config_overrides={},
        skills={},
        resumed_filename=None,
        repl_print=lambda *args, **kwargs: prints.append(" ".join(str(a) for a in args)),
        context_runtime=runtime,
    )

    events = runtime.store.list_events_after(0)
    assert runtime.store.get_state("active_topic_id") == second
    assert events[-1].event_type == "context_correction"
    assert second in "\n".join(prints)


@pytest.mark.asyncio
async def test_new_with_context_runtime_clears_short_term_only(tmp_path, monkeypatch):
    import ohmycode.storage.conversation as conv_mod

    monkeypatch.setattr(conv_mod, "CONVERSATIONS_DIR", tmp_path)
    runtime = _runtime(tmp_path / "ctx")
    topic_id = runtime.store.create_topic("long term topic", summary="keep me")
    runtime.store.set_state("active_topic_id", topic_id)
    conv = _conv()
    conv.add_user_message("hello")
    conv.auto_approved["bash"] = True
    set_conv = Mock()

    await handle_slash_command(
        cmd="/new",
        parts=["/new"],
        raw_input="/new",
        conv=conv,
        config=conv.config,
        config_overrides={},
        skills={},
        resumed_filename=None,
        set_conv=set_conv,
        context_runtime=runtime,
    )

    assert conv.messages == []
    assert conv.auto_approved == {}
    assert runtime.store.get_state("active_topic_id") == topic_id
    set_conv.assert_not_called()
