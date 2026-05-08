from __future__ import annotations

import shutil
from pathlib import Path

from ohmycode.context.runtime import ContextRuntime
from ohmycode.context.store import ContextStore
from ohmycode.core.messages import ImageBlock


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


def test_runtime_routes_chinese_query_to_chinese_topic():
    runtime = _runtime("runtime_chinese_route")
    runtime.store.create_topic("agent runtime", summary="tool loop provider stream")
    chinese_topic = runtime.store.create_topic("长期上下文", summary="单窗口 话题 投影")
    runtime.store.set_state("active_topic_id", "topic_agent_runtime")

    event_id = runtime.record_user_message("我们继续聊长期上下文和话题投影")
    prepared = runtime.prepare_for_turn(
        "我们继续聊长期上下文和话题投影",
        "base",
        event_id,
    )

    assert prepared.route.action == "switch"
    assert prepared.packet.topic_id == chinese_topic


def test_runtime_routes_mixed_language_query_to_mixed_topic():
    runtime = _runtime("runtime_mixed_route")
    runtime.store.create_topic("cli bugfix", summary="prompt rendering")
    mixed_topic = runtime.store.create_topic(
        "single window context",
        summary="话题 投影 topic slices",
    )
    runtime.store.set_state("active_topic_id", "topic_cli_bugfix")

    event_id = runtime.record_user_message("继续 context 里的话题投影")
    prepared = runtime.prepare_for_turn("继续 context 里的话题投影", "base", event_id)

    assert prepared.route.action == "switch"
    assert prepared.packet.topic_id == mixed_topic


def test_runtime_keeps_ambiguous_chinese_candidates_ambiguous():
    runtime = _runtime("runtime_chinese_ambiguous")
    runtime.store.create_topic("上下文缓存", summary="话题 投影")
    runtime.store.create_topic("上下文记忆", summary="话题 投影")

    event_id = runtime.record_user_message("上下文话题投影")
    prepared = runtime.prepare_for_turn("上下文话题投影", "base", event_id)

    assert prepared.route.action == "ambiguous"
    assert len(prepared.route.candidates) == 2


def test_runtime_chinese_topic_ids_do_not_collapse_to_default():
    runtime = _runtime("runtime_chinese_ids")

    first = runtime.store.create_topic("长期上下文")
    second = runtime.store.create_topic("话题投影")

    assert first != second
    assert first != "topic_default"
    assert second != "topic_default"


def test_record_user_message_stores_audit_metadata_without_image_data():
    runtime = _runtime("runtime_user_audit")
    image = ImageBlock(media_type="image/png", data="YWJjZA==")

    runtime.record_user_message(
        "expanded [image: sample.png]",
        raw_content="@sample.png",
        image_blocks=[image],
        ref_warnings=["warn"],
    )

    event = runtime.store.list_events_after(0)[0]
    audit = event.metadata["audit"]
    assert event.content == "expanded [image: sample.png]"
    assert audit["raw_content"] == "@sample.png"
    assert audit["expanded_content"] == "expanded [image: sample.png]"
    assert audit["ref_warnings"] == ["warn"]
    assert audit["images"][0]["media_type"] == "image/png"
    assert audit["images"][0]["base64_length"] == len("YWJjZA==")
    assert "sha256" in audit["images"][0]
    assert "data" not in audit["images"][0]


def test_record_tool_events_store_replayable_audit_payloads():
    runtime = _runtime("runtime_tool_audit")

    runtime.record_tool_call(
        "bash",
        '{"tool_use_id": "abc", "params": {"command": "echo hi"}}',
        tool_use_id="abc",
        params={"command": "echo hi"},
    )
    runtime.record_tool_result("abc", "hi", False)

    call, result = runtime.store.list_events_after(0)
    assert call.metadata["audit"] == {
        "tool_use_id": "abc",
        "tool_name": "bash",
        "params": {"command": "echo hi"},
    }
    assert result.metadata["audit"] == {
        "tool_use_id": "abc",
        "result": "hi",
        "is_error": False,
    }


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
