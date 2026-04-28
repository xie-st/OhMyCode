from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from ohmycode.context.curator import ContextCurator, build_provider_curate_fn
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
async def test_curator_ignores_invalid_json_without_marking_processed():
    store = _store("curator_bad_json")
    store.append_event("user_message", "hello")

    async def fake_curate(*args, **kwargs):
        return "not json"

    result = await ContextCurator(store, fake_curate).run_once()

    assert result.applied is False
    assert store.get_last_processed_event_id() == 0


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
