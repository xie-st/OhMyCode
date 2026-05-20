"""Bash tool — run commands in a shell."""

from __future__ import annotations

import asyncio
import contextlib
import locale

from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool

_DEFAULT_TIMEOUT = 120  # seconds
_MAX_OUTPUT_CHARS = 30_000  # ~7-10K tokens; keeps a single `find -r` from blowing the context window


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
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                return ToolResult(
                    output=f"Command timed out after {timeout} seconds.",
                    is_error=True,
                )

            output = _decode_output(stdout)
            output = _cap_output(output)
            is_error = proc.returncode != 0
            if is_error:
                output = (output or "") + f"\nExit code: {proc.returncode}"
            return ToolResult(output=output, is_error=is_error)

        except Exception as exc:
            import traceback as _tb
            detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            full = _tb.format_exc()
            return ToolResult(
                output=f"Error executing command: {detail}\n{full}",
                is_error=True,
            )


def _cap_output(text: str) -> str:
    """Truncate runaway command output so a single recursive listing can't
    poison the conversation history. Keeps the head + tail so error messages
    that print at the end of long output remain visible."""
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    head_budget = int(_MAX_OUTPUT_CHARS * 0.75)
    tail_budget = _MAX_OUTPUT_CHARS - head_budget
    head = text[:head_budget]
    tail = text[-tail_budget:]
    omitted = len(text) - head_budget - tail_budget
    notice = (
        f"\n\n[bash output truncated: kept first {head_budget:,} chars + "
        f"last {tail_budget:,} chars; dropped {omitted:,} chars in the middle. "
        f"Re-run with a narrower command (head, grep, --limit, etc.) for full output.]\n\n"
    )
    return head + notice + tail


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
