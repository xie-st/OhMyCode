"""Helpers for applying long-term context projection inside the REPL."""

from __future__ import annotations

from ohmycode.context.projection import build_topic_projection
from ohmycode.context.runtime import ContextRuntime, PreparedContext
from ohmycode.core.loop import ConversationLoop


def apply_context_projection(
    conv: ConversationLoop,
    runtime: ContextRuntime,
    prepared: PreparedContext,
    base_system_prompt: str,
) -> str:
    """Apply topic transcript projection when the current turn switches windows."""
    topic_id = prepared.packet.topic_id
    related_topic_ids = _existing_related_topic_ids(runtime, prepared.packet.related_topics)
    projection = build_topic_projection(
        store=runtime.store,
        base_system_prompt=base_system_prompt,
        active_topic_id=topic_id,
        related_topic_ids=related_topic_ids,
    )
    if _should_replace_messages(runtime, prepared):
        conv.messages = projection.messages
    runtime.store.set_state("last_projection_message_count", str(len(projection.messages)))
    runtime.store.set_state("last_projection_raw_tail_count", str(projection.raw_tail_event_count))
    return projection.system_prompt


def _should_replace_messages(runtime: ContextRuntime, prepared: PreparedContext) -> bool:
    if prepared.route.action in ("switch", "new_topic", "rebuild"):
        return True
    return runtime.store.load_compression_cache(prepared.packet.topic_id) is not None


def _existing_related_topic_ids(runtime: ContextRuntime, related_topics: list[str]) -> list[str]:
    return [topic_id for topic_id in related_topics if runtime.store.get_topic(topic_id) is not None]
