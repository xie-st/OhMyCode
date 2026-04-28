import sys

import pytest
from ohmycode.tools.base import ToolContext
from ohmycode.tools.bash import BashTool, _decode_output

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(mode="auto", agent_depth=0, cwd=str(tmp_path), is_sub_agent=False)

@pytest.mark.asyncio
async def test_bash_echo(ctx):
    tool = BashTool()
    result = await tool.execute({"command": "echo hello"}, ctx)
    assert result.output.strip() == "hello"
    assert not result.is_error

@pytest.mark.asyncio
async def test_bash_exit_code(ctx):
    tool = BashTool()
    result = await tool.execute({"command": "exit 1"}, ctx)
    assert result.is_error

@pytest.mark.asyncio
async def test_bash_timeout(ctx):
    tool = BashTool()
    command = f'"{sys.executable}" -c "import time; time.sleep(10)"'
    result = await tool.execute({"command": command, "timeout": 1}, ctx)
    assert result.is_error
    assert "timeout" in result.output.lower() or "timed out" in result.output.lower()


def test_decode_output_falls_back_to_windows_chinese_encoding():
    raw = "当前活跃话题".encode("gbk")

    decoded = _decode_output(raw)

    assert decoded == "当前活跃话题"
    assert "�" not in decoded


@pytest.mark.asyncio
async def test_bash_decodes_non_utf8_subprocess_output(ctx):
    tool = BashTool()
    command = (
        f'"{sys.executable}" -c '
        '"import sys; sys.stdout.buffer.write('
        '\'当前活跃话题\'.encode(\'gbk\'))"'
    )

    result = await tool.execute({"command": command}, ctx)

    assert result.output == "当前活跃话题"
    assert "�" not in result.output
