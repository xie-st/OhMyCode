import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ohmycode.tools.base import ToolContext
from ohmycode.tools.agent import AgentTool, MAX_AGENT_DEPTH
from ohmycode.core.messages import TextChunk, ToolCallStart, TurnComplete, TokenUsage


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(mode="auto", agent_depth=0, cwd=str(tmp_path), is_sub_agent=False)


@pytest.mark.asyncio
async def test_agent_depth_limit(ctx):
    """Test that agent respects depth limit."""
    tool = AgentTool()
    ctx.agent_depth = MAX_AGENT_DEPTH
    result = await tool.execute({"prompt": "test"}, ctx)
    assert result.is_error
    assert "depth limit" in result.output.lower()


@pytest.mark.asyncio
async def test_agent_properties(ctx):
    """Test that AgentTool has correct properties."""
    tool = AgentTool()
    assert tool.name == "agent"
    assert tool.concurrent_safe is False
    assert "prompt" in tool.parameters["properties"]


# ---------------------------------------------------------------------------
# SubAgentBox integration
# ---------------------------------------------------------------------------


def _fake_run_turn(*events):
    """Return an async generator that yields the given events."""
    async def _gen():
        for e in events:
            yield e
    return _gen


@pytest.mark.asyncio
async def test_push_tool_called_for_each_tool_call_start(ctx, tmp_path):
    """push_tool() is called once per ToolCallStart from the sub-loop."""
    push_calls = []

    class FakeBox:
        visible = False
        def push_tool(self, name): push_calls.append(name)
        def finish(self): pass
        def clear(self): pass

    fake_box = FakeBox()
    events = [
        ToolCallStart(tool_name="bash", tool_use_id="id1", params={}),
        ToolCallStart(tool_name="read", tool_use_id="id2", params={}),
        TextChunk(text="result"),
        TurnComplete(finish_reason="stop", usage=TokenUsage(10, 5, 15)),
    ]

    with patch("ohmycode._cli.output._is_interactive", return_value=True), \
         patch("ohmycode._cli.output.SubAgentBox", return_value=fake_box), \
         patch("ohmycode.core.loop.ConversationLoop") as MockLoop:
        inst = MockLoop.return_value
        inst.run_turn = _fake_run_turn(*events)
        inst.initialize = lambda: None
        inst.add_user_message = lambda p: None

        result = await AgentTool().execute({"prompt": "hello"}, ctx)

    assert push_calls == ["bash", "read"]
    assert result.output == "result"
    assert not result.is_error


@pytest.mark.asyncio
async def test_finish_called_on_success(ctx, tmp_path):
    """box.finish() is called when the sub-agent completes normally."""
    finish_called = []
    clear_called = []

    class FakeBox:
        visible = False
        def push_tool(self, name): pass
        def finish(self): finish_called.append(True)
        def clear(self): clear_called.append(True)

    events = [
        TextChunk(text="ok"),
        TurnComplete(finish_reason="stop", usage=TokenUsage(0, 0, 0)),
    ]

    with patch("ohmycode._cli.output._is_interactive", return_value=True), \
         patch("ohmycode._cli.output.SubAgentBox", return_value=FakeBox()), \
         patch("ohmycode.core.loop.ConversationLoop") as MockLoop:
        inst = MockLoop.return_value
        inst.run_turn = _fake_run_turn(*events)
        inst.initialize = lambda: None
        inst.add_user_message = lambda p: None

        await AgentTool().execute({"prompt": "q"}, ctx)

    assert finish_called, "finish() must be called on normal completion"
    assert not clear_called, "clear() must NOT be called on normal completion"


@pytest.mark.asyncio
async def test_clear_called_on_exception(ctx, tmp_path):
    """box.clear() is called (not finish) when the sub-loop raises."""
    finish_called = []
    clear_called = []

    class FakeBox:
        visible = True
        def push_tool(self, name): pass
        def finish(self): finish_called.append(True)
        def clear(self): clear_called.append(True)

    async def failing_run_turn():
        raise RuntimeError("provider error")
        yield  # make it an async generator

    with patch("ohmycode._cli.output._is_interactive", return_value=True), \
         patch("ohmycode._cli.output.SubAgentBox", return_value=FakeBox()), \
         patch("ohmycode.core.loop.ConversationLoop") as MockLoop:
        inst = MockLoop.return_value
        inst.run_turn = failing_run_turn
        inst.initialize = lambda: None
        inst.add_user_message = lambda p: None

        result = await AgentTool().execute({"prompt": "x"}, ctx)

    assert result.is_error
    assert clear_called, "clear() must be called when sub-agent errors"
    assert not finish_called, "finish() must NOT be called on error"


@pytest.mark.asyncio
async def test_no_box_when_not_interactive(ctx, tmp_path):
    """SubAgentBox is not instantiated when stdout is not a TTY."""
    box_created = []

    class TrackingBox:
        visible = False
        def __init__(self): box_created.append(self)
        def push_tool(self, name): pass
        def finish(self): pass
        def clear(self): pass

    events = [
        TextChunk(text="done"),
        TurnComplete(finish_reason="stop", usage=TokenUsage(0, 0, 0)),
    ]

    with patch("ohmycode._cli.output._is_interactive", return_value=False), \
         patch("ohmycode._cli.output.SubAgentBox", TrackingBox), \
         patch("ohmycode.core.loop.ConversationLoop") as MockLoop:
        inst = MockLoop.return_value
        inst.run_turn = _fake_run_turn(*events)
        inst.initialize = lambda: None
        inst.add_user_message = lambda p: None

        await AgentTool().execute({"prompt": "q"}, ctx)

    assert not box_created, "SubAgentBox must not be created when not interactive"


@pytest.mark.asyncio
async def test_no_box_for_nested_agent(ctx, tmp_path):
    """SubAgentBox is not created when agent_depth > 0 (nested sub-agent)."""
    ctx.agent_depth = 1
    box_created = []

    class TrackingBox:
        visible = False
        def __init__(self): box_created.append(self)
        def push_tool(self, name): pass
        def finish(self): pass
        def clear(self): pass

    events = [
        TextChunk(text="nested"),
        TurnComplete(finish_reason="stop", usage=TokenUsage(0, 0, 0)),
    ]

    with patch("ohmycode._cli.output._is_interactive", return_value=True), \
         patch("ohmycode._cli.output.SubAgentBox", TrackingBox), \
         patch("ohmycode.core.loop.ConversationLoop") as MockLoop:
        inst = MockLoop.return_value
        inst.run_turn = _fake_run_turn(*events)
        inst.initialize = lambda: None
        inst.add_user_message = lambda p: None

        await AgentTool().execute({"prompt": "nested"}, ctx)

    assert not box_created, "SubAgentBox must not be created inside a nested sub-agent"
