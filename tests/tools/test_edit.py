import pytest
from ohmycode.tools.base import ToolContext
from ohmycode.tools.edit import EditTool

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(mode="auto", agent_depth=0, cwd=str(tmp_path), is_sub_agent=False)

@pytest.mark.asyncio
async def test_edit_replace(ctx, tmp_path):
    f = tmp_path / "test.py"
    f.write_text("hello world\nfoo bar\n")
    tool = EditTool()
    result = await tool.execute(
        {"file_path": str(f), "old_string": "hello world", "new_string": "goodbye world"}, ctx)
    assert not result.is_error
    assert f.read_text() == "goodbye world\nfoo bar\n"

@pytest.mark.asyncio
async def test_edit_old_string_not_unique(ctx, tmp_path):
    f = tmp_path / "test.py"
    f.write_text("aaa\naaa\n")
    tool = EditTool()
    result = await tool.execute(
        {"file_path": str(f), "old_string": "aaa", "new_string": "bbb"}, ctx)
    assert result.is_error

@pytest.mark.asyncio
async def test_edit_old_string_not_found(ctx, tmp_path):
    f = tmp_path / "test.py"
    f.write_text("hello world\n")
    tool = EditTool()
    result = await tool.execute(
        {"file_path": str(f), "old_string": "xyz", "new_string": "abc"}, ctx)
    assert result.is_error
