"""Tests for the Renderer protocol and DispatchingRenderer dispatch."""

from __future__ import annotations

import pytest

from ohmycode.core.events import EventBus
from ohmycode.core.messages import (
    SubAgentDone,
    SubAgentToolUse,
    TextChunk,
    ThinkingChunk,
    TokenUsage,
    ToolCallResult,
    ToolCallStart,
    ToolCallStreaming,
    TurnComplete,
)
from ohmycode.core.renderer import DispatchingRenderer, Renderer


class _RecordingRenderer(DispatchingRenderer):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def on_text(self, event):
        self.calls.append(("text", event.text))

    async def on_thinking(self, event):
        self.calls.append(("thinking", event.text))

    async def on_tool_call_streaming(self, event):
        self.calls.append(("tool_streaming", event.tool_name))

    async def on_tool_call_start(self, event):
        self.calls.append(("tool_start", event.tool_name))

    async def on_tool_call_result(self, event):
        self.calls.append(("tool_result", event.is_error))

    async def on_sub_agent_tool_use(self, event):
        self.calls.append(("sub_use", event.tool_name))

    async def on_sub_agent_done(self, event):
        self.calls.append(("sub_done", event.is_error))

    async def on_turn_complete(self, event):
        self.calls.append(("done", event.finish_reason))


@pytest.mark.asyncio
async def test_dispatches_each_event_type():
    r = _RecordingRenderer()
    events = [
        TextChunk(text="hi"),
        ThinkingChunk(text="thought"),
        ToolCallStreaming(tool_name="bash", tool_use_id="t1"),
        ToolCallStart(tool_name="bash", tool_use_id="t1", params={}),
        ToolCallResult(tool_use_id="t1", result="ok", is_error=False),
        SubAgentToolUse(tool_name="agent"),
        SubAgentDone(is_error=False),
        TurnComplete(finish_reason="stop", usage=TokenUsage(0, 0, 0)),
    ]
    for e in events:
        await r.on_event(e)
    assert r.calls == [
        ("text", "hi"),
        ("thinking", "thought"),
        ("tool_streaming", "bash"),
        ("tool_start", "bash"),
        ("tool_result", False),
        ("sub_use", "agent"),
        ("sub_done", False),
        ("done", "stop"),
    ]


def test_renderer_protocol_is_satisfied_by_dispatching_renderer():
    assert isinstance(_RecordingRenderer(), Renderer)


@pytest.mark.asyncio
async def test_unhandled_event_type_is_ignored_silently():
    """An event type with no on_<x> handler must not raise."""

    class _Unknown:
        pass

    r = _RecordingRenderer()
    await r.on_event(_Unknown())  # noqa: type-check intentionally bypassed
    assert r.calls == []


@pytest.mark.asyncio
async def test_renderer_subscribed_to_bus_receives_events():
    bus = EventBus()
    r = _RecordingRenderer()
    bus.subscribe(r.on_event)

    await bus.publish(TextChunk(text="from bus"))
    assert r.calls == [("text", "from bus")]
