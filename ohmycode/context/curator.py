"""Async background curator for derived context state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Awaitable, Callable

from ohmycode.core.messages import UserMessage
from ohmycode.context.packet import ContextPacket
from ohmycode.context.store import ContextStore
from ohmycode.providers.base import stream_to_text


CurateFn = Callable[..., Awaitable[str]]

CURATOR_SYSTEM = """You are OhMyCode's background context curator.
Read recent append-only events and existing topic workspaces. Return compact JSON only.
Use this shape:
{"action":"keep|patch|rebuild|new_topic","topic":{"id":"","title":"","summary":"","status":""},"packet_patch":{"summary":"","decisions":[],"open_questions":[],"next_actions":[],"related_files":[],"related_topics":[],"global_memory":[]}}
Prefer small patches. Do not include markdown."""


@dataclass
class CuratorResult:
    applied: bool
    reason: str = ""


class ContextCurator:
    """Applies LLM-produced topic and packet updates to the context store."""

    def __init__(self, store: ContextStore, curate_fn: CurateFn) -> None:
        self.store = store
        self.curate_fn = curate_fn

    async def run_once(self) -> CuratorResult:
        last_id = self.store.get_last_processed_event_id()
        events = self.store.list_events_after(last_id)
        if not events:
            return CuratorResult(applied=False, reason="no_events")
        try:
            raw = await self.curate_fn(events=events, topics=self.store.list_topics())
        except Exception as exc:
            return CuratorResult(applied=False, reason=type(exc).__name__)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return CuratorResult(applied=False, reason="invalid_json")

        self._apply(data)
        self.store.set_last_processed_event_id(events[-1].id)
        return CuratorResult(applied=True)

    def _apply(self, data: dict) -> None:
        topic_data = data.get("topic") or {}
        topic_id = topic_data.get("id") or self.store.get_state("active_topic_id", "")
        if topic_id:
            self.store.update_topic(
                topic_id,
                title=topic_data.get("title"),
                summary=topic_data.get("summary"),
                status=topic_data.get("status"),
            )
        if not topic_id:
            return

        patch = data.get("packet_patch") or {}
        packet = self.store.load_packet(topic_id)
        topic = self.store.get_topic(topic_id)
        if packet is None and topic is not None:
            packet = ContextPacket(topic_id=topic.id, title=topic.title, summary=topic.summary)
        if packet is None:
            return

        for field in (
            "decisions",
            "open_questions",
            "next_actions",
            "related_files",
            "related_topics",
            "global_memory",
        ):
            if field in patch:
                setattr(packet, field, list(patch[field]))
        if "summary" in patch:
            packet.summary = patch["summary"]
        packet.version += 1
        self.store.save_packet(packet)

        slices_by_topic: dict[str, list[tuple[int, int]]] = {}
        for item in data.get("topic_slices") or []:
            slice_topic_id = item.get("topic_id") or topic_id
            start = int(item.get("start_event_id", 0) or 0)
            end = int(item.get("end_event_id", 0) or 0)
            slices_by_topic.setdefault(slice_topic_id, []).append((start, end))
        for slice_topic_id, ranges in slices_by_topic.items():
            self.store.save_topic_slices(slice_topic_id, ranges)


def build_provider_curate_fn(provider, model: str) -> CurateFn:
    async def _curate(*, events, topics) -> str:
        payload = {
            "events": [
                {
                    "id": event.id,
                    "type": event.event_type,
                    "content": event.content,
                    "metadata": event.metadata,
                    "created_at": event.created_at,
                }
                for event in events
            ],
            "topics": [
                {
                    "id": topic.id,
                    "title": topic.title,
                    "summary": topic.summary,
                    "status": topic.status,
                }
                for topic in topics
            ],
        }
        request = [
            UserMessage(
                "Update the long-term context state from this JSON:\n"
                + json.dumps(payload, ensure_ascii=False)
            )
        ]
        return await stream_to_text(provider, request, model, system=CURATOR_SYSTEM)

    return _curate
