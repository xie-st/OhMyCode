from __future__ import annotations

import json
from pathlib import Path

import pytest

from ohmycode.context.compression import TopicCompressor
from ohmycode.context.projection import build_topic_projection
from ohmycode.context.store import ContextStore
from ohmycode.core.messages import TextChunk, TokenUsage, TurnComplete


class SummaryProvider:
    name = "summary"

    async def stream(self, messages, tools, system, model, **kwargs):
        yield TextChunk(text="compressed summary")
        yield TurnComplete(finish_reason="stop", usage=TokenUsage(1, 1, 2))


def _store(tmp_path: Path) -> ContextStore:
    return ContextStore(tmp_path / "context.db")


@pytest.mark.asyncio
async def test_topic_compressor_saves_cache_and_keeps_raw_tail(tmp_path):
    store = _store(tmp_path)
    topic_id = store.create_topic("long topic")
    event_ids = []
    for idx in range(12):
        event_ids.append(store.append_event("user_message", f"message {idx} " + ("word " * 80)))
    store.save_topic_slices(topic_id, [(event_ids[0], event_ids[-1])])

    compressed = await TopicCompressor(
        store=store,
        provider=SummaryProvider(),
        model="test",
        token_budget=500,
        output_reserved=100,
        threshold=0.80,
    ).compress_if_needed(topic_id)

    assert compressed is True
    cache = store.load_compression_cache(topic_id)
    assert cache is not None
    assert cache.compressed_until_event_id == event_ids[-1]
    assert "compressed summary" in cache.messages_json

    tail_id = store.append_event("assistant_message", "new after compression")
    store.save_topic_slices(topic_id, [(event_ids[0], tail_id)])
    projection = build_topic_projection(store, "base", topic_id)

    assert projection.compressed_until_event_id == event_ids[-1]
    assert projection.raw_tail_event_count == 1
    assert projection.messages[-1].content == "new after compression"


@pytest.mark.asyncio
async def test_topic_compressor_does_not_rewrite_jsonl(tmp_path):
    store = _store(tmp_path)
    topic_id = store.create_topic("long topic")
    event_id = store.append_event("user_message", "word " * 500)
    store.save_topic_slices(topic_id, [(event_id, event_id)])
    event_file = next((tmp_path / "events").glob("*.jsonl"))
    before = event_file.read_text(encoding="utf-8")

    await TopicCompressor(
        store=store,
        provider=SummaryProvider(),
        model="test",
        token_budget=200,
        output_reserved=50,
        threshold=0.80,
    ).compress_if_needed(topic_id)

    after = event_file.read_text(encoding="utf-8")
    assert json.loads(before) == json.loads(after)
