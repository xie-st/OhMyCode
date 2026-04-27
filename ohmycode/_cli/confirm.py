"""User confirmation prompt for tool calls."""

from __future__ import annotations

import asyncio
import json
import sys

from rich.console import Console
from rich.markup import escape

from ohmycode._cli.output import ACCENT


_console = Console()


async def confirm_tool_call(tool_name: str, params: dict) -> str:
    """Show tool call details to the user and read y/n/a response."""
    params_preview = json.dumps(params, ensure_ascii=False)
    if len(params_preview) > 120:
        params_preview = params_preview[:117] + "..."

    _console.print()
    _console.print(f"  [bold yellow]⚠  Allow [{ACCENT}]{escape(tool_name)}[/]?[/]", highlight=False)
    _console.print(f"  [dim]{escape(params_preview)}[/dim]", highlight=False)
    _console.print()
    _console.print("  [bold]y[/][dim]es[/]  ·  [bold]n[/][dim]o[/]  ·  [bold]a[/][dim]lways[/]  ", end="")

    loop = asyncio.get_event_loop()
    try:
        answer = await loop.run_in_executor(None, sys.stdin.readline)
        return answer.strip().lower()[:1] or "n"
    except (EOFError, KeyboardInterrupt):
        return "n"
