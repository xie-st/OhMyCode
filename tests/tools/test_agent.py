import pytest
from ohmycode.tools.base import ToolContext
from ohmycode.tools.agent import AgentTool, MAX_AGENT_DEPTH


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(mode="auto", agent_depth=0, cwd=str(tmp_path), is_sub_agent=False)


@pytest.mark.asyncio
async def test_agent_depth_limit(ctx):
    """Test that agent respects depth limit."""
    tool = AgentTool()
    # Set depth to max, should fail
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
