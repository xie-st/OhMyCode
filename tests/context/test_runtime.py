from __future__ import annotations

import shutil
from pathlib import Path

from ohmycode.context.runtime import ContextRuntime
from ohmycode.context.store import ContextStore


def _runtime(name: str) -> ContextRuntime:
    root = Path.cwd() / "testtmp-manual" / name
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return ContextRuntime(ContextStore(root / "context.db"))


def test_runtime_creates_topic_and_dynamic_system_prompt():
    runtime = _runtime("runtime_new")
    event_id = runtime.record_user_message("Let's design the agent runtime")

    prepared = runtime.prepare_for_turn(
        "Let's design the agent runtime",
        base_system_prompt="You are OhMyCode.",
        last_event_id=event_id,
    )

    assert prepared.route.action == "new_topic"
    assert "You are OhMyCode." in prepared.system_prompt
    assert "Current Working Context" in prepared.system_prompt
    assert "agent runtime" in prepared.system_prompt.lower()


def test_runtime_keeps_active_packet_for_related_message():
    runtime = _runtime("runtime_keep")
    first_event = runtime.record_user_message("Let's design the context runtime")
    first = runtime.prepare_for_turn("Let's design the context runtime", "base", first_event)
    second_event = runtime.record_user_message("How should the context packet cache work?")

    second = runtime.prepare_for_turn(
        "How should the context packet cache work?",
        "base",
        second_event,
    )

    assert second.route.action in ("keep", "patch")
    assert second.packet.topic_id == first.packet.topic_id
    assert second.packet.version >= first.packet.version


def test_runtime_switches_to_existing_topic_when_query_matches_it():
    runtime = _runtime("runtime_switch")
    runtime.store.create_topic("agent runtime", summary="single-window context")
    bug_topic = runtime.store.create_topic("cli bugfix", summary="fix prompt rendering bug")
    runtime.store.set_state("active_topic_id", "topic_agent_runtime")

    event_id = runtime.record_user_message("Please fix the CLI prompt rendering bug")
    prepared = runtime.prepare_for_turn(
        "Please fix the CLI prompt rendering bug",
        "base",
        event_id,
    )

    assert prepared.route.action == "switch"
    assert prepared.packet.topic_id == bug_topic


def test_runtime_reports_ambiguous_topic_candidates():
    runtime = _runtime("runtime_ambiguous")
    runtime.store.create_topic("context cache", summary="packet cache context")
    runtime.store.create_topic("context memory", summary="memory context packet")

    event_id = runtime.record_user_message("context packet")
    prepared = runtime.prepare_for_turn("context packet", "base", event_id)

    assert prepared.route.action == "ambiguous"
    assert len(prepared.route.candidates) == 2


def test_runtime_coalesces_topic_compression_tasks():
    import asyncio

    runtime = _runtime("runtime_compression_coalesce")
    topic_id = runtime.store.create_topic("long topic")
    calls = 0
    gate = asyncio.Event()

    async def fake_run():
        nonlocal calls
        calls += 1
        if calls == 1:
            await gate.wait()

    async def scenario():
        first = runtime.request_topic_compression(topic_id, fake_run)
        second = runtime.request_topic_compression(topic_id, fake_run)
        gate.set()
        await first
        return first, second

    first, second = asyncio.run(scenario())

    assert first is second
    assert calls == 2
