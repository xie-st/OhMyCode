"""Lazy topic-level compression cache generation."""

from __future__ import annotations

from ohmycode.context.projection import _messages_from_events, _topic_events, messages_to_json
from ohmycode.context.store import ContextStore
from ohmycode.core.context import ContextManager


class TopicCompressor:
    """Compress one topic transcript into a derived cache when it grows too large."""

    def __init__(
        self,
        store: ContextStore,
        provider,
        model: str,
        token_budget: int,
        output_reserved: int,
        threshold: float = 0.80,
    ) -> None:
        self.store = store
        self.provider = provider
        self.model = model
        self.threshold = threshold
        self.context_mgr = ContextManager(token_budget, output_reserved)

    async def compress_if_needed(self, topic_id: str) -> bool:
        events = _topic_events(self.store, topic_id)
        if not events:
            return False
        messages = _messages_from_events(events)
        if self.context_mgr.get_usage_ratio(messages, "") < self.threshold:
            return False
        compressed = await self.context_mgr.auto_compact(
            messages,
            self.provider,
            self.model,
        )
        self.store.save_compression_cache(
            topic_id=topic_id,
            compressed_until_event_id=max(event.id for event in events),
            messages_json=messages_to_json(compressed),
            summary="",
        )
        return True
