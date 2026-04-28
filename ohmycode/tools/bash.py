"""Bash tool — run commands in a shell."""

from __future__ import annotations

import asyncio
import locale

from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool

_DEFAULT_TIMEOUT = 120  # seconds


@register_tool
class BashTool(Tool):
    name = "bash"
    description = "Run a bash command in the shell and return its output."
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to run",
            },
            "timeout": {
                "type": "number",
                "description": "Timeout in seconds (default 120)",
            },
        },
        "required": ["command"],
    }
    concurrent_safe = False

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        command = params["command"]
        timeout = params.get("timeout", _DEFAULT_TIMEOUT)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=ctx.cwd,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                return ToolResult(
                    output=f"Command timed out after {timeout} seconds.",
                    is_error=True,
                )

            output = _decode_output(stdout)
            is_error = proc.returncode != 0
            if is_error:
                output = (output or "") + f"\nExit code: {proc.returncode}"
            return ToolResult(output=output, is_error=is_error)

        except Exception as exc:
            return ToolResult(output=f"Error executing command: {exc}", is_error=True)


def _decode_output(data: bytes) -> str:
    """Decode subprocess output without corrupting common non-UTF-8 terminals."""
    if not data:
        return ""
    encodings = [
        "utf-8-sig",
        locale.getpreferredencoding(False),
        "gbk",
        "cp936",
        "mbcs",
    ]
    seen: set[str] = set()
    for encoding in encodings:
        if not encoding:
            continue
        key = encoding.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")
