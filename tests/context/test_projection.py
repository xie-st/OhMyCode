from __future__ import annotations

from pathlib import Path

from ohmycode.context.packet import ContextPacket
from ohmycode.context.projection import (
    build_topic_projection,
    messages_from_json,
    messages_to_json,
)
from ohmycode.context.store import ContextStore
from ohmycode.core.messages import AssistantMessage, UserMessage


def _store(tmp_path: Path) -> ContextStore:
    return ContextStore(tmp_path / "context.db")


def test_projection_rebuilds_active_topic_messages_from_slices(tmp_path):
    store = _store(tmp_path)
    topic_id = store.create_topic("agent runtime", summary="runtime summary")
    other_id = store.create_topic("ui design", summary="ui packet")
    store.save_packet(ContextPacket(topic_id=topic_id, title="agent runtime", summary="runtime summary"))
    store.save_packet(ContextPacket(topic_id=other_id, title="ui design", summary="ui packet"))
    e1 = store.append_event("user_message", "A1")
    e2 = store.append_event("assistant_message", "A2")
    store.append_event("user_message", "B1")
    e4 = store.append_event("user_message", "A3")
    store.save_topic_slices(topic_id, [(e1, e2), (e4, e4)])

    projection = build_topic_projection(
        store=store,
        base_system_prompt="base",
        active_topic_id=topic_id,
        related_topic_ids=[other_id],
    )

    assert [m.content for m in projection.messages] == ["A1", "A2", "A3"]
    assert isinstance(projection.messages[0], UserMessage)
    assert isinstance(projection.messages[1], AssistantMessage)
    assert "runtime summary" in projection.system_prompt
    assert "Related Topic Packets" in projection.system_prompt
    assert "ui packet" in projection.system_prompt


def test_projection_uses_compressed_history_plus_raw_tail(tmp_path):
    store = _store(tmp_path)
    topic_id = store.create_topic("long topic", summary="long")
    store.save_packet(ContextPacket(topic_id=topic_id, title="long topic", summary="long"))
    first = store.append_event("user_message", "old raw")
    second = store.append_event("assistant_message", "new raw")
    store.save_topic_slices(topic_id, [(first, second)])
    compressed_messages = [UserMessage("compressed old")]
    store.save_compression_cache(
        topic_id=topic_id,
        compressed_until_event_id=first,
        messages_json=messages_to_json(compressed_messages),
        summary="compressed",
    )

    projection = build_topic_projection(
        store=store,
        base_system_prompt="base",
        active_topic_id=topic_id,
    )

    assert [m.content for m in projection.messages] == ["compressed old", "new raw"]
    assert projection.compressed_until_event_id == first
    assert projection.raw_tail_event_count == 1


def test_message_json_round_trips_text_messages():
    messages = [UserMessage("hello"), AssistantMessage("hi")]

    loaded = messages_from_json(messages_to_json(messages))

    assert [m.content for m in loaded] == ["hello", "hi"]
