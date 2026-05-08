"""Build topic-scoped transcript projections for the foreground model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ohmycode.context.store import ContextEvent, ContextStore
from ohmycode.core.messages import (
    AssistantMessage,
    Message,
    ToolResultMessage,
    ToolUseBlock,
    UserMessage,
)


@dataclass
class TranscriptProjection:
    system_prompt: str
    messages: list[Message]
    active_topic_id: str
    related_topic_ids: list[str] = field(default_factory=list)
    compressed_until_event_id: int | None = None
    raw_tail_event_count: int = 0


def build_topic_projection(
    store: ContextStore,
    base_system_prompt: str,
    active_topic_id: str,
    related_topic_ids: list[str] | None = None,
) -> TranscriptProjection:
    related_topic_ids = related_topic_ids or []
    cache = store.load_compression_cache(active_topic_id)
    compressed_until = cache.compressed_until_event_id if cache else None
    messages = messages_from_json(cache.messages_json) if cache else []
    raw_events = _topic_events(store, active_topic_id, after_event_id=compressed_until or 0)
    messages.extend(_messages_from_events(raw_events))

    return TranscriptProjection(
        system_prompt=_render_system_prompt(
            store,
            base_system_prompt,
            active_topic_id,
            related_topic_ids,
            compressed_until,
            len(raw_events),
        ),
        messages=messages,
        active_topic_id=active_topic_id,
        related_topic_ids=related_topic_ids,
        compressed_until_event_id=compressed_until,
        raw_tail_event_count=len(raw_events),
    )


def messages_to_json(messages: list[Message]) -> str:
    data = []
    for message in messages:
        if isinstance(message, UserMessage):
            data.append({"role": "user", "content": message.content})
        elif isinstance(message, AssistantMessage):
            data.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "tool_use_id": tc.tool_use_id,
                        "tool_name": tc.tool_name,
                        "params": tc.params,
                    }
                    for tc in message.tool_calls
                ],
            })
        elif isinstance(message, ToolResultMessage):
            data.append({
                "role": "tool",
                "tool_use_id": message.tool_use_id,
                "content": message.content,
                "is_error": message.is_error,
            })
    return json.dumps(data, ensure_ascii=False)


def messages_from_json(raw: str) -> list[Message]:
    messages: list[Message] = []
    for item in json.loads(raw or "[]"):
        role = item.get("role")
        if role == "user":
            messages.append(UserMessage(item.get("content", "")))
        elif role == "assistant":
            messages.append(AssistantMessage(
                item.get("content", ""),
                tool_calls=_tool_calls_from_json(item.get("tool_calls") or []),
            ))
        elif role == "tool":
            messages.append(ToolResultMessage(
                item.get("tool_use_id", ""),
                item.get("content", ""),
                bool(item.get("is_error", False)),
            ))
    return messages


def _topic_events(
    store: ContextStore,
    topic_id: str,
    after_event_id: int = 0,
) -> list[ContextEvent]:
    events: list[ContextEvent] = []
    seen_ids: set[int] = set()
    for topic_slice in store.list_topic_slices(topic_id):
        start = max(topic_slice.start_event_id, after_event_id + 1)
        if start <= topic_slice.end_event_id:
            chunk = store.list_events_range(start, topic_slice.end_event_id)
            chunk = _extend_events_for_tool_results(store, chunk, topic_slice.end_event_id)
            for event in chunk:
                if event.id > after_event_id and event.id not in seen_ids:
                    events.append(event)
                    seen_ids.add(event.id)
    return sorted(events, key=lambda event: event.id)


def _extend_events_for_tool_results(
    store: ContextStore,
    events: list[ContextEvent],
    end_event_id: int,
) -> list[ContextEvent]:
    pending = _pending_tool_ids(events)
    next_event_id = end_event_id + 1
    max_event_id = store.get_max_event_id()
    while pending and next_event_id <= max_event_id:
        next_events = store.list_events_range(next_event_id, next_event_id)
        if not next_events:
            break
        event = next_events[0]
        if event.event_type not in ("tool_call", "tool_result"):
            break
        events.append(event)
        if event.event_type == "tool_result":
            pending.discard(event.metadata.get("tool_use_id", ""))
        next_event_id += 1
    return events


def _messages_from_events(events: list[ContextEvent]) -> list[Message]:
    messages: list[Message] = []
    open_tool_ids: set[str] = set()
    for event in events:
        if event.event_type == "user_message":
            _append_missing_tool_results(messages, open_tool_ids)
            messages.append(UserMessage(event.content))
        elif event.event_type == "assistant_message":
            _append_missing_tool_results(messages, open_tool_ids)
            tool_calls = _tool_calls_from_json(event.metadata.get("tool_calls") or [])
            open_tool_ids.update(tc.tool_use_id for tc in tool_calls)
            messages.append(AssistantMessage(event.content, tool_calls=tool_calls))
        elif event.event_type == "tool_result":
            tool_use_id = event.metadata.get("tool_use_id", "")
            if tool_use_id in open_tool_ids:
                messages.append(ToolResultMessage(
                    tool_use_id,
                    event.content,
                    bool(event.metadata.get("is_error", False)),
                ))
                open_tool_ids.discard(tool_use_id)
    _append_missing_tool_results(messages, open_tool_ids)
    return messages


def _pending_tool_ids(events: list[ContextEvent]) -> set[str]:
    pending: set[str] = set()
    for event in events:
        if event.event_type == "assistant_message":
            pending.update(
                tc.tool_use_id
                for tc in _tool_calls_from_json(event.metadata.get("tool_calls") or [])
            )
        elif event.event_type == "tool_result":
            pending.discard(event.metadata.get("tool_use_id", ""))
    return pending


def _append_missing_tool_results(messages: list[Message], open_tool_ids: set[str]) -> None:
    for tool_use_id in sorted(open_tool_ids):
        messages.append(
            ToolResultMessage(
                tool_use_id,
                "Tool result omitted from transcript projection.",
                is_error=True,
            )
        )
    open_tool_ids.clear()


def _render_system_prompt(
    store: ContextStore,
    base_system_prompt: str,
    active_topic_id: str,
    related_topic_ids: list[str],
    compressed_until_event_id: int | None,
    raw_tail_event_count: int,
) -> str:
    sections = [base_system_prompt.rstrip()]
    active_packet = store.load_packet(active_topic_id)
    if active_packet is not None:
        sections.append(active_packet.render())
    related = [store.load_packet(topic_id) for topic_id in related_topic_ids]
    related = [packet for packet in related if packet is not None]
    if related:
        sections.append("# Related Topic Packets")
        sections.extend(packet.render(max_chars=8_000) for packet in related)
    sections.append(
        "# Transcript Projection\n"
        f"active_topic_id: {active_topic_id}\n"
        f"compressed_until_event_id: {compressed_until_event_id or ''}\n"
        f"raw_tail_event_count: {raw_tail_event_count}\n"
    )
    return "\n\n".join(sections)


def _tool_calls_from_json(items: list[dict]) -> list[ToolUseBlock]:
    return [
        ToolUseBlock(
            tool_use_id=item.get("tool_use_id", ""),
            tool_name=item.get("tool_name", ""),
            params=item.get("params") or {},
        )
        for item in items
    ]
