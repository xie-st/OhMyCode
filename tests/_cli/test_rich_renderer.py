"""State-machine tests for the RichRenderer wrapping the dispatch protocol."""

from __future__ import annotations

import pytest

from ohmycode._cli.output import RichRenderer
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.loop import ConversationLoop
from ohmycode.core.messages import (
    SubAgentDone,
    TextChunk,
    TokenUsage,
    ToolCallResult,
    ToolCallStart,
    TurnComplete,
)


@pytest.fixture
def conv():
    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    return ConversationLoop(config=config)


@pytest.mark.asyncio
async def test_on_turn_start_resets_state(conv):
    r = RichRenderer(conv)
    r._tool_count = 7
    r._text_printed = True
    r._first_event_seen = True
    r.finish_reason = "error"

    await r.on_turn_start()
    try:
        assert r._tool_count == 0
        assert r._text_printed is False
        assert r._first_event_seen is False
        assert r.finish_reason == "stop"
    finally:
        await r.on_turn_end()


@pytest.mark.asyncio
async def test_first_event_marks_seen(conv):
    r = RichRenderer(conv)
    await r.on_turn_start()
    try:
        assert r._first_event_seen is False
        await r.on_event(TextChunk(text="hi"))
        assert r._first_event_seen is True
    finally:
        await r.on_turn_end()


@pytest.mark.asyncio
async def test_tool_count_advances_per_tool_call_start(conv):
    r = RichRenderer(conv)
    await r.on_turn_start()
    try:
        await r.on_event(ToolCallStart(tool_name="bash", tool_use_id="t1", params={}))
        await r.on_event(ToolCallStart(tool_name="read", tool_use_id="t2", params={}))
        assert r._tool_count == 2
    finally:
        await r.on_turn_end()


@pytest.mark.asyncio
async def test_turn_complete_records_finish_reason_and_resets_count(conv):
    r = RichRenderer(conv)
    await r.on_turn_start()
    try:
        await r.on_event(ToolCallStart(tool_name="bash", tool_use_id="t1", params={}))
        await r.on_event(
            TurnComplete(finish_reason="max_turns", usage=TokenUsage(0, 0, 0))
        )
        assert r.finish_reason == "max_turns"
        assert r._tool_count == 0
    finally:
        await r.on_turn_end()


@pytest.mark.asyncio
async def test_sub_agent_done_clears_box_state(conv):
    r = RichRenderer(conv)
    await r.on_turn_start()
    try:
        # Simulate a sub-agent box getting created (sub_agent_box != None)
        from ohmycode._cli.output import SubAgentBox
        r._sub_agent_box = SubAgentBox()
        await r.on_event(SubAgentDone(is_error=True))
        assert r._sub_agent_box is None
    finally:
        await r.on_turn_end()


@pytest.mark.asyncio
async def test_text_event_marks_text_printed(conv):
    r = RichRenderer(conv)
    await r.on_turn_start()
    try:
        await r.on_event(TextChunk(text="anything"))
        assert r._text_printed is True
    finally:
        await r.on_turn_end()


@pytest.mark.asyncio
async def test_text_after_tool_call_resets_then_re_marks(conv):
    """A ToolCallStart should reset text_printed; the next TextChunk re-sets it."""
    r = RichRenderer(conv)
    await r.on_turn_start()
    try:
        await r.on_event(TextChunk(text="part1"))
        assert r._text_printed is True
        await r.on_event(ToolCallStart(tool_name="read", tool_use_id="t1", params={}))
        assert r._text_printed is False
        await r.on_event(
            ToolCallResult(tool_use_id="t1", result="ok", is_error=False)
        )
        await r.on_event(TextChunk(text="part2"))
        assert r._text_printed is True
    finally:
        await r.on_turn_end()


@pytest.mark.asyncio
async def test_renderer_protocol_satisfied(conv):
    from ohmycode.core.renderer import Renderer
    assert isinstance(RichRenderer(conv), Renderer)
