"""CLI entry point: argument parsing and dispatch.

The actual modes live under `_cli/` (REPL, single-shot) and `commands/`
(standalone subcommands like `vchange`).
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import threading
from typing import Any

# Enable ANSI escape code processing on Windows (cmd.exe / conhost).
# Tests reload this module to verify the guard runs only on win32.
if sys.platform == "win32":
    import ctypes
    try:
        kernel32 = ctypes.windll.kernel32
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass  # Not a real console (e.g. redirected output); safe to ignore

from rich.console import Console

from ohmycode.core.permissions import MODES


console = Console()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ohmycode",
        description="OhMyCode — a minimal AI coding assistant",
    )
    parser.add_argument(
        "-p", "--prompt",
        metavar="PROMPT",
        help="Run a single prompt and exit (non-interactive mode).",
    )
    parser.add_argument(
        "--provider",
        metavar="PROVIDER",
        help="LLM provider name (e.g. openai).",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        help="Model name (e.g. gpt-4o).",
    )
    parser.add_argument(
        "--mode",
        metavar="MODE",
        choices=list(MODES),
        help=f"Permission mode: {' | '.join(MODES)}.",
    )
    parser.add_argument(
        "--api-key",
        metavar="KEY",
        dest="api_key",
        help="API key for the provider.",
    )
    parser.add_argument(
        "--base-url",
        metavar="URL",
        dest="base_url",
        help="Custom base URL for the provider API.",
    )
    parser.add_argument(
        "--resume",
        nargs="?",
        const="",
        default=None,
        help="Resume a previous conversation",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help="Subcommand: vchange [-N|N]",
    )
    parser.add_argument(
        "command_arg",
        nargs="?",
        default=None,
        help="Argument for subcommand",
    )
    return parser.parse_args(argv)


def run() -> int:
    """CLI main: parse args, dispatch to run_single, run_repl, or subcommands."""
    args = parse_args()

    if args.command == "vchange":
        from ohmycode.commands.vchange import run_vchange
        step = None
        if args.command_arg is not None:
            try:
                step = int(args.command_arg)
            except ValueError:
                console.print("[red]Usage: ohmycode vchange [-N|N]  (e.g. ohmycode vchange -1)[/red]")
                return 1
        return run_vchange(step)

    config_overrides: dict[str, Any] = {
        "provider": args.provider,
        "model": args.model,
        "mode": args.mode,
        "api_key": args.api_key,
        "base_url": args.base_url,
    }

    if args.resume is not None:
        config_overrides["_resume"] = args.resume

    if args.prompt:
        from ohmycode._cli.single_shot import run_single
        return asyncio.run(run_single(args.prompt, config_overrides))

    from ohmycode._cli.repl import run_repl
    cancel_event = threading.Event()
    old_handler = signal.signal(signal.SIGINT, lambda s, f: cancel_event.set())
    try:
        return asyncio.run(run_repl(config_overrides, cancel_event=cancel_event))
    finally:
        signal.signal(signal.SIGINT, old_handler)
