from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from ohmycode.context.curator import CURATOR_SYSTEM, ContextCurator, build_provider_curate_fn
from ohmycode.context.packet import ContextPacket
from ohmycode.core.messages import TextChunk, TokenUsage, TurnComplete
from ohmycode.context.store import ContextStore


def _store(name: str) -> ContextStore:
    root = Path.cwd() / "testtmp-manual" / name
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return ContextStore(root / "context.db")


@pytest.mark.asyncio
async def test_curator_applies_patch_json():
    store = _store("curator_patch")
    store.append_event("user_message", "design async curator")
    topic_id = store.create_topic("context curator", summary="old")
    store.set_state("active_topic_id", topic_id)

    async def fake_curate(*args, **kwargs):
        return (
            '{"action":"patch","topic":{"id":"%s","summary":"new summary"},'
            '"packet_patch":{"decisions":["use async curator"]}}' % topic_id
        )

    result = await ContextCurator(store, fake_curate).run_once()

    assert result.applied is True
    assert store.get_topic(topic_id).summary == "new summary"
    assert store.load_packet(topic_id).decisions == ["use async curator"]
    assert store.get_last_processed_event_id() == 1


@pytest.mark.asyncio
async def test_curator_applies_topic_slices():
    store = _store("curator_slices")
    store.append_event("user_message", "start runtime")
    store.append_event("assistant_message", "continue runtime")
    topic_id = store.create_topic("agent runtime")
    store.set_state("active_topic_id", topic_id)

    async def fake_curate(*args, **kwargs):
        return json.dumps({
            "action": "patch",
            "topic": {"id": topic_id},
            "topic_slices": [
                {"topic_id": topic_id, "start_event_id": 1, "end_event_id": 2},
                {"topic_id": topic_id, "start_event_id": 3, "end_event_id": 2},
            ],
        })

    result = await ContextCurator(store, fake_curate).run_once()

    assert result.applied is True
    slices = store.list_topic_slices(topic_id)
    assert [(s.start_event_id, s.end_event_id) for s in slices] == [(1, 2)]


@pytest.mark.asyncio
async def test_curator_keep_advances_watermark_without_bumping_semantic_version():
    store = _store("curator_keep_watermark")
    store.append_event("user_message", "hello")
    store.append_event("assistant_message", "hi")
    topic_id = store.create_topic("context runtime", summary="current summary")
    store.set_state("active_topic_id", topic_id)
    store.save_packet(
        ContextPacket(
            topic_id=topic_id,
            title="context runtime",
            summary="current summary",
            version=3,
            last_event_id=0,
        )
    )

    async def fake_curate(*args, **kwargs):
        return json.dumps({"action": "keep", "topic": {"id": topic_id}})

    result = await ContextCurator(store, fake_curate).run_once()
    packet = store.load_packet(topic_id)

    assert result.applied is True
    assert packet.version == 3
    assert packet.last_event_id == 2
    assert store.get_last_processed_event_id() == 2


@pytest.mark.asyncio
async def test_curator_semantic_patch_bumps_version_and_advances_watermark():
    store = _store("curator_semantic_patch")
    store.append_event("user_message", "design async curator")
    store.append_event("assistant_message", "use semantic versions")
    topic_id = store.create_topic("context curator", summary="old")
    store.set_state("active_topic_id", topic_id)
    store.save_packet(
        ContextPacket(
            topic_id=topic_id,
            title="context curator",
            summary="old",
            version=4,
            last_event_id=0,
        )
    )

    async def fake_curate(*args, **kwargs):
        return json.dumps({
            "action": "patch",
            "topic": {"id": topic_id},
            "packet_patch": {
                "summary": "new summary",
                "decisions": ["version means semantic content changed"],
            },
        })

    result = await ContextCurator(store, fake_curate).run_once()
    packet = store.load_packet(topic_id)

    assert result.applied is True
    assert packet.version == 5
    assert packet.last_event_id == 2
    assert packet.summary == "new summary"
    assert packet.decisions == ["version means semantic content changed"]


@pytest.mark.asyncio
async def test_curator_topic_summary_updates_packet_summary():
    store = _store("curator_topic_summary_to_packet")
    store.append_event("user_message", "summarize topic")
    topic_id = store.create_topic("context curator", summary="old")
    store.set_state("active_topic_id", topic_id)
    store.save_packet(
        ContextPacket(
            topic_id=topic_id,
            title="context curator",
            summary="old",
            version=2,
        )
    )

    async def fake_curate(*args, **kwargs):
        return json.dumps({
            "action": "patch",
            "topic": {"id": topic_id, "summary": "topic-level summary"},
        })

    result = await ContextCurator(store, fake_curate).run_once()
    packet = store.load_packet(topic_id)

    assert result.applied is True
    assert packet.summary == "topic-level summary"
    assert packet.version == 3


def test_curator_prompt_declares_topic_slices_contract():
    assert "topic_slices" in CURATOR_SYSTEM
    assert "topic_slices_mode" in CURATOR_SYSTEM


@pytest.mark.asyncio
async def test_curator_merges_topic_slices_by_default():
    store = _store("curator_merge_slices")
    for idx in range(6):
        store.append_event("user_message", f"event {idx}")
    topic_id = store.create_topic("agent runtime")
    store.set_state("active_topic_id", topic_id)
    store.save_topic_slices(topic_id, [(1, 2)])

    async def fake_curate(*args, **kwargs):
        return json.dumps({
            "action": "patch",
            "topic": {"id": topic_id},
            "topic_slices": [
                {"topic_id": topic_id, "start_event_id": 4, "end_event_id": 5},
            ],
        })

    result = await ContextCurator(store, fake_curate).run_once()

    assert result.applied is True
    slices = store.list_topic_slices(topic_id)
    assert [(s.start_event_id, s.end_event_id) for s in slices] == [(1, 2), (4, 5)]


@pytest.mark.asyncio
async def test_curator_replaces_topic_slices_when_requested():
    store = _store("curator_replace_slices")
    for idx in range(6):
        store.append_event("user_message", f"event {idx}")
    topic_id = store.create_topic("agent runtime")
    store.set_state("active_topic_id", topic_id)
    store.save_topic_slices(topic_id, [(1, 2), (4, 5)])

    async def fake_curate(*args, **kwargs):
        return json.dumps({
            "action": "rebuild",
            "topic": {"id": topic_id},
            "topic_slices_mode": "replace",
            "topic_slices": [
                {"topic_id": topic_id, "start_event_id": 6, "end_event_id": 6},
                {"topic_id": topic_id, "start_event_id": 8, "end_event_id": 7},
            ],
        })

    result = await ContextCurator(store, fake_curate).run_once()

    assert result.applied is True
    slices = store.list_topic_slices(topic_id)
    assert [(s.start_event_id, s.end_event_id) for s in slices] == [(6, 6)]


@pytest.mark.asyncio
async def test_curator_ignores_invalid_json_without_marking_processed():
    store = _store("curator_bad_json")
    store.append_event("user_message", "hello")

    async def fake_curate(*args, **kwargs):
        return "not json"

    result = await ContextCurator(store, fake_curate).run_once()

    assert result.applied is False
    assert store.get_last_processed_event_id() == 0


@pytest.mark.asyncio
async def test_curator_self_heals_when_high_water_mark_exceeds_max_event(capfd):
    """If last_processed_event_id is past the end of the event log (e.g.
    after external truncation or a project-slug collision), the curator
    should reset its mark to 0 and reprocess history rather than
    perpetually returning ``no_events``."""
    store = _store("curator_self_heal")
    # Two real events (IDs 1 and 2)
    store.append_event("user_message", "hi")
    store.append_event("assistant_message", "hello")
    # Stale curator state: claims to have processed up to 282
    store.set_last_processed_event_id(282)

    topic_id = store.create_topic("test topic", summary="t")
    store.set_state("active_topic_id", topic_id)

    async def fake_curate(*args, **kwargs):
        return '{"action":"keep","topic":{"id":"%s"}}' % topic_id

    result = await ContextCurator(store, fake_curate).run_once()

    # After self-heal + reprocess, the run completes normally and the mark
    # is reset to the highest real event ID (2).
    assert result.applied is True
    assert store.get_last_processed_event_id() == 2

    # The diagnostic warning is printed to stderr.
    captured = capfd.readouterr()
    assert "exceeds max_event_id" in captured.err


@pytest.mark.asyncio
async def test_curator_does_not_self_heal_when_mark_is_zero():
    """A fresh store has last_processed_event_id=0 with no events. That is
    the *normal* empty state, not an inconsistency — do not log a warning,
    do not reset, just return no_events as before."""
    store = _store("curator_fresh_empty")
    # No events, no curator state set (defaults to 0)

    async def fake_curate(*args, **kwargs):
        raise AssertionError("curate_fn should not be called when no events")

    result = await ContextCurator(store, fake_curate).run_once()
    assert result.applied is False
    assert result.reason == "no_events"


def test_get_max_event_id_returns_zero_for_empty_store():
    store = _store("max_event_empty")
    assert store.get_max_event_id() == 0


def test_get_max_event_id_returns_highest_id():
    store = _store("max_event_populated")
    store.append_event("user_message", "a")
    store.append_event("assistant_message", "b")
    store.append_event("tool_call", "c")
    assert store.get_max_event_id() == 3


@pytest.mark.asyncio
async def test_runtime_coalesces_curator_tasks():
    from ohmycode.context.runtime import ContextRuntime

    store = _store("curator_coalesce")
    runtime = ContextRuntime(store)
    calls = 0

    gate = asyncio.Event()

    async def fake_run():
        nonlocal calls
        calls += 1
        if calls == 1:
            await gate.wait()

    first = runtime.request_curator_run(fake_run)
    second = runtime.request_curator_run(fake_run)
    gate.set()
    await first

    assert first is second
    assert calls == 2


@pytest.mark.asyncio
async def test_build_provider_curate_fn_returns_provider_json():
    class JsonProvider:
        name = "json"

        async def stream(self, messages, tools, system, model, **kwargs):
            assert tools == []
            assert "context curator" in system.lower()
            assert model == "test-model"
            assert "events" in messages[0].content
            yield TextChunk(text=json.dumps({"action": "keep"}))
            yield TurnComplete(finish_reason="stop", usage=TokenUsage(1, 1, 2))

    fn = build_provider_curate_fn(JsonProvider(), "test-model")
    raw = await fn(events=[], topics=[])

    assert json.loads(raw) == {"action": "keep"}
