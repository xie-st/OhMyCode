from __future__ import annotations

from pathlib import Path

from ohmycode._cli.context_flow import apply_context_projection
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.context.runtime import ContextRuntime
from ohmycode.context.store import ContextStore
from ohmycode.core.loop import ConversationLoop


def _runtime(tmp_path: Path) -> ContextRuntime:
    return ContextRuntime(ContextStore(tmp_path / "context.db"))


def _conv() -> ConversationLoop:
    conv = ConversationLoop(OhMyCodeConfig(provider="mock", model="test", mode="auto"))
    conv._system_prompt = "base"
    return conv


def test_apply_context_projection_preserves_messages_for_same_topic(tmp_path):
    runtime = _runtime(tmp_path)
    first_event_id = runtime.record_user_message("design runtime")
    runtime.prepare_for_turn("design runtime", "base", first_event_id)
    event_id = runtime.record_user_message("continue runtime design")
    prepared = runtime.prepare_for_turn("continue runtime design", "base", event_id)
    conv = _conv()
    conv.add_user_message("previous same topic")

    prompt = apply_context_projection(conv, runtime, prepared, "base")

    assert [message.content for message in conv.messages] == ["previous same topic"]
    assert "Current Working Context" in prompt


def test_apply_context_projection_replaces_messages_on_topic_switch(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.store.create_topic("agent runtime", summary="A")
    bug_topic = runtime.store.create_topic("cli bugfix", summary="B")
    runtime.store.set_state("active_topic_id", "topic_agent_runtime")
    first = runtime.store.append_event("user_message", "old bug question")
    second = runtime.store.append_event("assistant_message", "old bug answer")
    runtime.store.save_topic_slices(bug_topic, [(first, second)])
    conv = _conv()
    conv.add_user_message("unrelated active topic")

    event_id = runtime.record_user_message("Please fix the CLI bug")
    prepared = runtime.prepare_for_turn("Please fix the CLI bug", "base", event_id)
    prompt = apply_context_projection(conv, runtime, prepared, "base")

    assert prepared.route.action == "switch"
    assert [message.content for message in conv.messages] == ["old bug question", "old bug answer"]
    assert "active_topic_id" in prompt
