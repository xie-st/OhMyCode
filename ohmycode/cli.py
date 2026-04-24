"""CLI entry: REPL and one-shot prompt mode, rich streaming output."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

# Enable ANSI escape code processing on Windows (cmd.exe / conhost)
if sys.platform == "win32":
    import ctypes
    try:
        kernel32 = ctypes.windll.kernel32
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass  # Not a real console (e.g. redirected output); safe to ignore

from rich import box as rich_box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

from ohmycode.config.config import load_config, OhMyCodeConfig
from ohmycode.core.loop import ConversationLoop
from ohmycode.core.file_ref import expand_file_refs
from ohmycode.skills.loader import scan_skills
from ohmycode.storage.conversation import load_conversation

from ohmycode._cli.output import render_stream, ACCENT
from ohmycode._cli.prompt_session import build_prompt_session, REPL_PROMPT_LINE_PREFIX
from ohmycode._cli.repl_commands import handle_slash_command

console = Console()


def _build_repl_welcome_text(
    model_display: str,
    mode: str,
    n_skills: int,
) -> Text:
    """Claw-inspired: big block letters + subtitle + aligned meta rows."""
    _OHMY_BLOCK_LINES = (
        " ██████╗██╗  ██╗███╗   ███╗██╗   ██╗\n"
        "██╔═══██╗██║  ██║████╗ ████║╚██╗ ██╔╝\n"
        "██║   ██║███████║██╔████╔██║ ╚████╔╝ \n"
        "██║   ██║██╔══██║██║╚██╔╝██║  ╚██╔╝  \n"
        "╚██████╔╝██║  ██║██║ ╚═╝ ██║   ██║   \n"
        " ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝   ╚═╝   "
    )
    t = Text()
    t.append(_OHMY_BLOCK_LINES, style=ACCENT)
    t.append("  ")
    t.append("Code", style=f"bold {ACCENT}")
    t.append(" v0.1.0\n\n", style="dim")
    label_w = 12
    t.append("Model".ljust(label_w), style="dim")
    t.append(f"{model_display}\n", style="bold")
    t.append("Mode".ljust(label_w), style="dim")
    t.append(f"{mode}\n", style="green")
    t.append("Skills".ljust(label_w), style="dim")
    t.append(f"{n_skills} available\n", style="dim")
    return t


# ── Argument parsing ────────────────────────────────────────────────────────────


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
        choices=["default", "auto", "plan"],
        help="Permission mode: default | auto | plan.",
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


# ── Version switch (vchange) ──────────────────────────────────────────────────


def run_vchange(step: int | None = None) -> int:
    """Version switch: step=None shows status, step=-1 goes back, step=1 goes forward."""
    cwd = os.getcwd()

    r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        console.print("[red]Not in a git repository.[/red]")
        return 1

    if step is None:
        log = subprocess.run(["git", "log", "--oneline", "-5"],
                             capture_output=True, text=True, cwd=cwd)
        head = subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True, cwd=cwd).stdout.strip()
        console.print(f"\n  [bold]Recent commits:[/]")
        for line in log.stdout.strip().splitlines():
            sha = line.split()[0]
            if head.startswith(sha):
                console.print(f"    [green]▸ {line}[/]  [green]← HEAD[/]")
            else:
                console.print(f"    [dim]  {line}[/]")
        console.print(f"\n  [dim]Usage: ohmycode vchange -1 (back) / ohmycode vchange 1 (forward)[/]")
        return 0

    if step == 0:
        console.print("[dim]Nothing to do.[/dim]")
        return 0

    all_log = subprocess.run(["git", "log", "main", "--oneline", "--reverse"],
                             capture_output=True, text=True, cwd=cwd)
    all_commits = all_log.stdout.strip().splitlines()
    if not all_commits:
        console.print("[yellow]No commits found.[/yellow]")
        return 1

    head_sha = subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True, cwd=cwd).stdout.strip()
    current_idx = -1
    for i, line in enumerate(all_commits):
        sha = line.split()[0]
        if head_sha.startswith(sha):
            current_idx = i
            break

    if current_idx == -1:
        console.print("[yellow]HEAD is not on main branch history.[/yellow]")
        return 1

    target_idx = current_idx + step
    if target_idx < 0:
        console.print("[yellow]Already at the oldest commit. Cannot go back further.[/yellow]")
        return 1
    if target_idx >= len(all_commits):
        console.print("[yellow]Already at the latest commit. Cannot go forward.[/yellow]")
        return 1

    target_line = all_commits[target_idx]
    target_sha = target_line.split()[0]

    console.print(f"\n  [bold]Current:[/] {all_commits[current_idx]}")
    console.print(f"  [bold]Target: [/] {target_line}")

    status = subprocess.run(["git", "status", "--porcelain"],
                            capture_output=True, text=True, cwd=cwd)
    if status.stdout.strip():
        n = len(status.stdout.strip().splitlines())
        console.print(f"  [yellow]Warning: {n} uncommitted change{'s' if n > 1 else ''} will be lost[/yellow]")

    console.print("  [bold]Confirm? (y/n):[/bold] ", end="")
    answer = input().strip().lower()
    if answer == "y":
        subprocess.run(["git", "checkout", target_sha, "--force"],
                       capture_output=True, text=True, cwd=cwd)
        console.print(f"  [green]✓ Switched to: {target_line}[/green]")
        console.print("  [dim]Restart ohmycode to load the changed code.[/dim]")
        return 0
    else:
        console.print("  [dim]Cancelled.[/dim]")
        return 0


# ── Tool confirmation ───────────────────────────────────────────────────────────


async def confirm_tool_call(tool_name: str, params: dict) -> str:
    """Show tool call details to the user and read y/n/a response."""
    params_preview = json.dumps(params, ensure_ascii=False)
    if len(params_preview) > 120:
        params_preview = params_preview[:117] + "..."

    console.print()
    console.print(f"  [bold yellow]⚠  Allow [{ACCENT}]{escape(tool_name)}[/]?[/]", highlight=False)
    console.print(f"  [dim]{escape(params_preview)}[/dim]", highlight=False)
    console.print()
    console.print("  [bold]y[/][dim]es[/]  ·  [bold]n[/][dim]o[/]  ·  [bold]a[/][dim]lways[/]  ", end="")

    loop = asyncio.get_event_loop()
    try:
        answer = await loop.run_in_executor(None, sys.stdin.readline)
        return answer.strip().lower()[:1] or "n"
    except (EOFError, KeyboardInterrupt):
        return "n"


# ── One-shot prompt mode ─────────────────────────────────────────────────────


async def run_single(prompt: str, config_overrides: dict[str, Any]) -> int:
    """Run a single prompt then exit; returns exit code."""
    config = load_config(config_overrides)
    conv = ConversationLoop(config=config, confirm_fn=confirm_tool_call)
    conv.initialize()
    expanded_prompt, _ = expand_file_refs(prompt, os.getcwd())
    conv.add_user_message(expanded_prompt)

    try:
        await render_stream(conv)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        return 130

    return 0


# ── REPL mode ─────────────────────────────────────────────────────────────────


async def run_repl(config_overrides: dict[str, Any], cancel_event: threading.Event | None = None) -> int:
    """Interactive REPL loop; supports /exit, /clear, /mode, etc."""
    config = load_config(config_overrides)
    conv = ConversationLoop(config=config, confirm_fn=confirm_tool_call)
    conv.initialize()
    available_skills = scan_skills()

    # Session ID isolates this process's saved conversations from other concurrent processes
    session_id = str(uuid.uuid4())[:8]

    # Mutable state shared with callbacks
    current_mode = config.mode
    resumed_filename: str | None = None

    def get_current_mode() -> str:
        return current_mode

    def set_current_mode(m: str) -> None:
        nonlocal current_mode
        current_mode = m

    def set_conv(new_conv: ConversationLoop) -> None:
        nonlocal conv
        conv = new_conv

    def set_config(new_config: OhMyCodeConfig) -> None:
        nonlocal config
        config = new_config

    def set_resumed_filename(f: str | None) -> None:
        nonlocal resumed_filename
        resumed_filename = f

    # Resume conversation
    if "_resume" in config_overrides and config_overrides["_resume"] is not None:
        result = load_conversation(config_overrides.get("_resume", ""))
        if result:
            conv.messages, metadata = result
            resumed_filename = metadata.get("filename")
            console.print(f"[dim]Resumed conversation from {metadata.get('saved_at', 'unknown')}[/dim]\n")
        else:
            console.print("[yellow]No conversation found to resume.[/yellow]\n")

    # Welcome banner
    model_display = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", config.model)
    welcome_body = _build_repl_welcome_text(
        model_display=model_display,
        mode=config.mode,
        n_skills=len(available_skills),
    )
    banner = Panel(
        welcome_body,
        title=f"[bold {ACCENT}]◆ OhMyCode[/]",
        title_align="left",
        border_style=ACCENT,
        box=rich_box.ROUNDED,
        padding=(2, 2),
    )
    console.print()
    console.print(banner)
    console.print()
    console.print(
        f"  [dim]Type[/] [bold {ACCENT}]/skills[/] [dim]for commands ·[/] "
        f"[bold {ACCENT}]/status[/] [dim]for context usage ·[/] [bold {ACCENT}]/exit[/] "
        f"[dim]to quit ·[/] [bold]Ctrl+C[/] [dim]to cancel[/]"
    )
    console.print()

    # Build prompt_toolkit session (or fall back to plain input)
    use_prompt_toolkit = False
    pt_session = None
    _get_prompt = None
    try:
        pt_session, _get_prompt = build_prompt_session(
            available_skills, conv, config, get_current_mode
        )
        use_prompt_toolkit = True
    except ImportError:
        pass

    _pt_console = Console(file=sys.__stdout__, force_terminal=True, highlight=False)

    def _repl_print(*args: Any, **kwargs: Any) -> None:
        if use_prompt_toolkit and pt_session is not None:
            from prompt_toolkit.patch_stdout import patch_stdout
            with patch_stdout():
                _pt_console.print(*args, **kwargs)
        else:
            console.print(*args, **kwargs)

    def _repl_print_plain(*args: Any, **kwargs: Any) -> None:
        if use_prompt_toolkit and pt_session is not None:
            from prompt_toolkit.patch_stdout import patch_stdout
            with patch_stdout():
                print(*args, **kwargs, flush=True)
        else:
            print(*args, **kwargs, flush=True)

    _INTERRUPT = object()

    async def _read_line() -> str | None | object:
        if use_prompt_toolkit and pt_session is not None:
            try:
                return await pt_session.prompt_async(_get_prompt)
            except KeyboardInterrupt:
                return _INTERRUPT
            except EOFError:
                return None
        else:
            loop = asyncio.get_event_loop()
            try:
                line = await loop.run_in_executor(None, lambda: input("❯ "))
                return line
            except KeyboardInterrupt:
                return _INTERRUPT
            except EOFError:
                return None

    async def _stream_with_cancel(c: ConversationLoop) -> str:
        """Run render_stream as a Task; cancel it if cancel_event fires."""
        render_task = asyncio.create_task(render_stream(c))
        if cancel_event is None:
            return await render_task
        stop_polling = threading.Event()

        def _poll_cancel():
            while not stop_polling.is_set():
                if cancel_event.wait(timeout=0.1):
                    return

        cancel_fut: asyncio.Future = asyncio.ensure_future(
            asyncio.to_thread(_poll_cancel)
        )
        done, _ = await asyncio.wait(
            {render_task, cancel_fut},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_fut in done:
            cancel_event.clear()
            stop_polling.set()
            render_task.cancel()
            try:
                await render_task
            except asyncio.CancelledError:
                pass
            return "cancelled"
        else:
            stop_polling.set()
            cancel_fut.cancel()
            try:
                await cancel_fut
            except (asyncio.CancelledError, Exception):
                pass
            return render_task.result()

    while True:
        user_input = await _read_line()

        if user_input is _INTERRUPT:
            if cancel_event:
                cancel_event.clear()
            _repl_print("\n[yellow](Use /exit to quit)[/yellow]")
            continue

        if user_input is None:
            _repl_print_plain("\nGoodbye.")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # ── Slash commands ───────────────────────────────────────────────
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()

            result = await handle_slash_command(
                cmd=cmd,
                parts=parts,
                raw_input=user_input,
                conv=conv,
                config=config,
                config_overrides=config_overrides,
                skills=available_skills,
                resumed_filename=resumed_filename,
                session_id=session_id,
                repl_print=_repl_print,
                repl_print_plain=_repl_print_plain,
                stream_fn=_stream_with_cancel,
                confirm_tool_call=confirm_tool_call,
                get_current_mode=get_current_mode,
                set_current_mode=set_current_mode,
                set_conv=set_conv,
                set_config=set_config,
                set_resumed_filename=set_resumed_filename,
            )
            if isinstance(result, int):
                return result
            continue

        # ── Normal user message ──────────────────────────────────────────
        expanded_input, image_blocks, ref_warnings = expand_file_refs(user_input, os.getcwd())
        for w in ref_warnings:
            _repl_print(f"  [yellow]{w}[/yellow]")
        conv.add_user_message(expanded_input, image_blocks=image_blocks or None)

        finish_reason = await _stream_with_cancel(conv)
        if finish_reason == "max_turns":
            _repl_print("[yellow]Reached maximum turns limit.[/yellow]")
        elif finish_reason == "cancelled":
            _repl_print("\n[yellow](Interrupted — partial reply saved to history. Continue or /exit)[/yellow]")

    return 0


# ── Main entry ────────────────────────────────────────────────────────────────


def run() -> int:
    """CLI main: parse args, run run_single, run_repl, or subcommands."""
    args = parse_args()

    if args.command == "vchange":
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
        return asyncio.run(run_single(args.prompt, config_overrides))
    else:
        cancel_event = threading.Event()
        old_handler = signal.signal(signal.SIGINT, lambda s, f: cancel_event.set())
        try:
            return asyncio.run(run_repl(config_overrides, cancel_event=cancel_event))
        finally:
            signal.signal(signal.SIGINT, old_handler)
