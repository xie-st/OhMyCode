"""One-shot prompt mode: run a single prompt then exit."""

from __future__ import annotations

import os
from typing import Any

from rich.console import Console

from ohmycode.config.config import load_config
from ohmycode.core.file_ref import expand_file_refs
from ohmycode.core.loop import ConversationLoop
from ohmycode._cli.confirm import confirm_tool_call
from ohmycode._cli.output import render_stream


_console = Console()


async def run_single(prompt: str, config_overrides: dict[str, Any]) -> int:
    """Run a single prompt then exit; returns exit code."""
    config = load_config(config_overrides)
    conv = ConversationLoop(config=config, confirm_fn=confirm_tool_call)
    conv.initialize()
    expanded_prompt, _, _ = expand_file_refs(prompt, os.getcwd())
    conv.add_user_message(expanded_prompt)

    try:
        await render_stream(conv)
    except KeyboardInterrupt:
        _console.print("\n[yellow]Interrupted.[/yellow]")
        return 130

    return 0
