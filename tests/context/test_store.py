from __future__ import annotations

import shutil
from pathlib import Path

from ohmycode.context.packet import ContextPacket
from ohmycode.context.store import ContextStore


def _db_path(name: str) -> Path:
    root = Path.cwd() / "testtmp-manual" / name
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root / "context.db"


def test_store_initializes_sqlite_and_appends_events():
    store = ContextStore(_db_path("store_events"))

    first = store.append_event("user_message", "hello", {"source": "test"})
    second = store.append_event("assistant_message", "hi")

    assert first == 1
    assert second == 2
    events = store.list_events_after(0)
    assert [event.event_type for event in events] == ["user_message", "assistant_message"]
    assert events[0].metadata["source"] == "test"


def test_store_keeps_events_append_only_when_topics_change():
    store = ContextStore(_db_path("store_append_only"))
    event_id = store.append_event("user_message", "design context runtime")
    topic_id = store.create_topic("context runtime", summary="initial summary")

    store.link_event_to_topic(topic_id, event_id)
    store.update_topic(topic_id, summary="updated summary", status="active")

    events = store.list_events_after(0)
    assert len(events) == 1
    assert events[0].content == "design context runtime"
    assert store.get_topic(topic_id).summary == "updated summary"


def test_store_saves_packets_and_curator_state():
    store = ContextStore(_db_path("store_packets"))
    topic_id = store.create_topic("agent runtime", summary="long-lived context")
    packet = ContextPacket(
        topic_id=topic_id,
        title="agent runtime",
        summary="long-lived context",
        decisions=["use async curator"],
        version=3,
    )

    store.save_packet(packet)
    store.set_last_processed_event_id(42)

    loaded = store.load_packet(topic_id)
    assert loaded is not None
    assert loaded.decisions == ["use async curator"]
    assert loaded.version == 3
    assert store.get_last_processed_event_id() == 42


def test_store_writes_events_to_daily_jsonl_and_reads_ranges():
    db_path = _db_path("store_jsonl")
    store = ContextStore(db_path)

    first = store.append_event("user_message", "day one", created_at="2026-04-28T10:00:00+00:00")
    second = store.append_event("assistant_message", "day two", created_at="2026-04-29T10:00:00+00:00")

    assert first == 1
    assert second == 2
    assert (db_path.parent / "events" / "2026-04-28.jsonl").exists()
    assert (db_path.parent / "events" / "2026-04-29.jsonl").exists()

    events = store.list_events_range(1, 2)
    assert [event.content for event in events] == ["day one", "day two"]
    assert [event.event_type for event in store.list_events_after(1)] == ["assistant_message"]


def test_store_saves_topic_slices_and_compression_cache():
    store = ContextStore(_db_path("store_slices_cache"))
    topic_id = store.create_topic("agent runtime")

    store.save_topic_slices(topic_id, [(1, 3), (8, 12), (20, 19)])
    slices = store.list_topic_slices(topic_id)

    assert [(s.start_event_id, s.end_event_id) for s in slices] == [(1, 3), (8, 12)]
    assert store.count_topic_slices(topic_id) == 2

    store.save_compression_cache(
        topic_id=topic_id,
        compressed_until_event_id=12,
        messages_json='[{"role":"user","content":"compressed"}]',
        summary="old part compressed",
    )
    cache = store.load_compression_cache(topic_id)

    assert cache is not None
    assert cache.compressed_until_event_id == 12
    assert "compressed" in cache.messages_json
