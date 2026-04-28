import pytest
from unittest.mock import patch
from ohmycode.tools.base import ToolContext
from ohmycode.tools.agent import AgentTool, MAX_AGENT_DEPTH
from ohmycode.core.messages import (
    SubAgentDone,
    SubAgentToolUse,
    TextChunk,
    ToolCallStart,
    TurnComplete,
    TokenUsage,
)


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(mode="auto", agent_depth=0, cwd=str(tmp_path), is_sub_agent=False)


@pytest.mark.asyncio
async def test_agent_depth_limit(ctx):
    """AgentTool refuses to spawn past MAX_AGENT_DEPTH."""
    tool = AgentTool()
    ctx.agent_depth = MAX_AGENT_DEPTH
    result = await tool.execute({"prompt": "test"}, ctx)
    assert result.is_error
    assert "depth limit" in result.output.lower()


@pytest.mark.asyncio
async def test_agent_properties(ctx):
    """AgentTool exposes expected name, schema, and serial-execution flag."""
    tool = AgentTool()
    assert tool.name == "agent"
    assert tool.concurrent_safe is False
    assert "prompt" in tool.parameters["properties"]


# ---------------------------------------------------------------------------
# Event emission via ctx.event_emitter
# ---------------------------------------------------------------------------


def _fake_run_turn(*events):
    async def _gen():
        for e in events:
            yield e
    return _gen


@pytest.mark.asyncio
async def test_emits_sub_agent_tool_use_per_tool_call(ctx):
    """One SubAgentToolUse event per ToolCallStart from the inner sub-loop."""
    events_seen: list = []
    ctx.event_emitter = events_seen.append

    inner_events = [
        ToolCallStart(tool_name="bash", tool_use_id="id1", params={}),
        ToolCallStart(tool_name="read", tool_use_id="id2", params={}),
        TextChunk(text="result"),
        TurnComplete(finish_reason="stop", usage=TokenUsage(10, 5, 15)),
    ]

    with patch("ohmycode.core.loop.ConversationLoop") as MockLoop:
        inst = MockLoop.return_value
        inst.run_turn = _fake_run_turn(*inner_events)
        inst.initialize = lambda: None
        inst.add_user_message = lambda p: None

        result = await AgentTool().execute({"prompt": "hello"}, ctx)

    tool_uses = [e for e in events_seen if isinstance(e, SubAgentToolUse)]
    dones = [e for e in events_seen if isinstance(e, SubAgentDone)]
    assert [e.tool_name for e in tool_uses] == ["bash", "read"]
    assert len(dones) == 1 and dones[0].is_error is False
    assert result.output == "result"
    assert not result.is_error


@pytest.mark.asyncio
async def test_emits_sub_agent_done_with_is_error_on_failure(ctx):
    """SubAgentDone(is_error=True) when the sub-loop raises."""
    events_seen: list = []
    ctx.event_emitter = events_seen.append

    async def failing_run_turn():
        raise RuntimeError("provider error")
        yield  # make it an async generator

    with patch("ohmycode.core.loop.ConversationLoop") as MockLoop:
        inst = MockLoop.return_value
        inst.run_turn = failing_run_turn
        inst.initialize = lambda: None
        inst.add_user_message = lambda p: None

        result = await AgentTool().execute({"prompt": "x"}, ctx)

    dones = [e for e in events_seen if isinstance(e, SubAgentDone)]
    assert result.is_error
    assert len(dones) == 1 and dones[0].is_error is True


@pytest.mark.asyncio
async def test_silent_when_emitter_is_none(ctx):
    """No emitter wired = no crash; tool still runs and returns output."""
    ctx.event_emitter = None  # default; explicit for clarity

    inner_events = [
        ToolCallStart(tool_name="bash", tool_use_id="id1", params={}),
        TextChunk(text="ok"),
        TurnComplete(finish_reason="stop", usage=TokenUsage(0, 0, 0)),
    ]

    with patch("ohmycode.core.loop.ConversationLoop") as MockLoop:
        inst = MockLoop.return_value
        inst.run_turn = _fake_run_turn(*inner_events)
        inst.initialize = lambda: None
        inst.add_user_message = lambda p: None

        result = await AgentTool().execute({"prompt": "q"}, ctx)

    assert result.output == "ok"
    assert not result.is_error


@pytest.mark.asyncio
async def test_emitter_exception_does_not_break_tool(ctx):
    """A misbehaving emitter callback must not propagate out of execute()."""
    def boom(_event):
        raise ValueError("emitter blew up")
    ctx.event_emitter = boom

    inner_events = [
        ToolCallStart(tool_name="bash", tool_use_id="id1", params={}),
        TextChunk(text="ok"),
        TurnComplete(finish_reason="stop", usage=TokenUsage(0, 0, 0)),
    ]

    with patch("ohmycode.core.loop.ConversationLoop") as MockLoop:
        inst = MockLoop.return_value
        inst.run_turn = _fake_run_turn(*inner_events)
        inst.initialize = lambda: None
        inst.add_user_message = lambda p: None

        result = await AgentTool().execute({"prompt": "q"}, ctx)

    assert result.output == "ok"
    assert not result.is_error


def test_no_imports_from_cli_layer():
    """Sanity check: tools.agent must not import _cli.* (orthogonality)."""
    import ast
    import inspect
    from ohmycode.tools import agent as agent_mod

    tree = ast.parse(inspect.getsource(agent_mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "_cli" not in alias.name, f"forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or "_cli" not in node.module, (
                f"forbidden import: from {node.module}"
            )
