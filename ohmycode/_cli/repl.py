"""Interactive REPL loop with slash-command dispatch and Ctrl+C cancellation."""

from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
import uuid
from typing import Any

from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel

from ohmycode.config.config import load_config, OhMyCodeConfig
from ohmycode.core.file_ref import expand_file_refs
from ohmycode.core.loop import ConversationLoop
from ohmycode.skills.loader import scan_skills
from ohmycode.storage.conversation import load_conversation

from ohmycode._cli.confirm import confirm_tool_call
from ohmycode._cli.output import render_stream, ACCENT
from ohmycode._cli.prompt_session import build_prompt_session
from ohmycode._cli.repl_commands import handle_slash_command
from ohmycode._cli.welcome import build_repl_welcome_text


_console = Console()


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
            _console.print(f"[dim]Resumed conversation from {metadata.get('saved_at', 'unknown')}[/dim]\n")
        else:
            _console.print("[yellow]No conversation found to resume.[/yellow]\n")

    # Welcome banner
    model_display = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", config.model)
    welcome_body = build_repl_welcome_text(
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
    _console.print()
    _console.print(banner)
    _console.print()
    _console.print(
        f"  [dim]Type[/] [bold {ACCENT}]/skills[/] [dim]for commands ·[/] "
        f"[bold {ACCENT}]/status[/] [dim]for context usage ·[/] [bold {ACCENT}]/exit[/] "
        f"[dim]to quit ·[/] [bold]Ctrl+C[/] [dim]to cancel[/]"
    )
    _console.print()

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
            _console.print(*args, **kwargs)

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
                cancel_event=cancel_event,
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
