"""REPL slash command handlers."""

from __future__ import annotations

import os
from typing import Any, Callable

from ohmycode.config.config import load_config, OhMyCodeConfig
from ohmycode.core.loop import ConversationLoop
from ohmycode.memory.memory import (
    BTreeMemoryStore,
    get_project_memory_dir,
    VALID_CATEGORIES,
    extract_memories_with_box,
)
from ohmycode.skills.loader import load_skill, SkillInfo
from ohmycode.storage.conversation import (
    save_conversation,
    list_unextracted_conversations,
    mark_conversation_memories_extracted,
    load_conversation,
)
from ohmycode._cli.output import MemoryBox

# Re-imported here so callers don't need a separate import for confirm_tool_call
from ohmycode._cli.output import ACCENT  # noqa: F401 (used by callers via this module)


async def handle_slash_command(
    cmd: str,
    parts: list[str],
    raw_input: str,
    conv: ConversationLoop,
    config: OhMyCodeConfig,
    config_overrides: dict[str, Any],
    skills: dict[str, SkillInfo],
    resumed_filename: str | None,
    session_id: str = "",
    repl_print: Callable = lambda *a, **k: None,
    repl_print_plain: Callable = lambda *a, **k: None,
    stream_fn: Callable = lambda *a, **k: None,
    confirm_tool_call: Callable = lambda *a, **k: None,
    get_current_mode: Callable[[], str] = lambda: "",
    set_current_mode: Callable[[str], None] = lambda m: None,
    set_conv: Callable[[ConversationLoop], None] = lambda c: None,
    set_config: Callable[[OhMyCodeConfig], None] = lambda c: None,
    set_resumed_filename: Callable[[str | None], None] = lambda f: None,
) -> str | int:
    """Dispatch a slash command. Returns 'continue', 'break', or an int exit code."""
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("/exit", "/quit"):
        repl_print_plain("Goodbye.")
        if conv.messages:
            save_conversation(
                conv.messages, config.provider, config.model, config.mode,
                filename=resumed_filename,
                session_id=session_id,
                memories_extracted=False,
            )
            repl_print_plain("Conversation saved.")
        if conv._provider:
            pending = list_unextracted_conversations(session_id)
            if pending:
                n = len(pending)
                repl_print_plain(f"  Extracting memories from {n} conversation{'s' if n > 1 else ''}...")
                _store = BTreeMemoryStore(get_project_memory_dir(os.getcwd()))
                _store.ensure_tree()
                for i, filename in enumerate(pending, 1):
                    result = load_conversation(filename)
                    if result is None:
                        mark_conversation_memories_extracted(filename)
                        continue
                    msgs, _ = result
                    box = MemoryBox()
                    try:
                        memories = await extract_memories_with_box(msgs, conv._provider, config.model, box)
                    except Exception:
                        memories = []
                    box.clear()
                    for m in memories:
                        _store.save(m["name"], m["type"], m["content"])
                    mark_conversation_memories_extracted(filename)
                    count = len(memories)
                    repl_print_plain(f"  ✓ Conversation {i} ({count} memor{'y' if count == 1 else 'ies'} saved)")
        return 0

    if cmd == "/clear":
        conv.messages.clear()
        conv.auto_approved.clear()
        repl_print("[dim]Conversation cleared.[/dim]")
        return "continue"

    if cmd == "/new":
        if conv.messages:
            try:
                saved = save_conversation(
                    conv.messages, config.provider, config.model, config.mode,
                    session_id=session_id,
                    memories_extracted=False,
                )
                repl_print(f"[dim]Conversation saved: {saved}[/dim]")
            except Exception as e:
                repl_print(f"[red]Failed to save conversation: {e}[/red]")
                repl_print("[dim]Conversation not reset. Fix the error and try again.[/dim]")
                return "continue"
        new_conv = ConversationLoop(config=config, confirm_fn=confirm_tool_call)
        new_conv.initialize()
        set_conv(new_conv)
        set_resumed_filename(None)
        repl_print("[dim]New conversation started.[/dim]")
        return "continue"

    if cmd == "/mode":
        if not args:
            repl_print(f"[dim]Current mode: {get_current_mode()}[/dim]")
            repl_print("[dim]Usage: /mode <default|auto|plan>[/dim]")
        else:
            new_mode = args.strip()
            if new_mode not in ("default", "auto", "plan"):
                repl_print(f"[red]Unknown mode: {new_mode}[/red]")
            else:
                set_current_mode(new_mode)
                new_overrides = dict(config_overrides)
                new_overrides["mode"] = new_mode
                new_config = load_config(new_overrides)
                new_conv = ConversationLoop(config=new_config, confirm_fn=confirm_tool_call)
                new_conv.initialize()
                set_config(new_config)
                set_conv(new_conv)
                repl_print(f"[dim]Mode switched to: {new_mode}[/dim]")
        return "continue"

    if cmd == "/status":
        status = conv.get_status_snapshot()
        repl_print()
        repl_print("  [bold]Session status[/]")
        repl_print(
            f"    [dim]Model:[/] {status['provider']} / {status['model']}    "
            f"[dim]Mode:[/] {status['mode']}"
        )
        repl_print(
            f"    [dim]Messages:[/] {status['message_count']}    "
            f"[dim]Context:[/] {status['used_tokens']:,} / {status['effective_window']:,} tokens "
            f"([bold]{status['usage_percent']:.1f}%[/])"
        )
        repl_print(
            f"    [dim]Budget:[/] {status['token_budget']:,} total, "
            f"{status['output_reserved']:,} reserved for output"
        )
        repl_print(f"    [dim]Compression stage:[/] {status['compression_stage']}")
        repl_print()
        return "continue"

    if raw_input.startswith("/memory"):
        mem_parts = raw_input.split(maxsplit=2)
        _store = BTreeMemoryStore(get_project_memory_dir(os.getcwd()))
        _store.ensure_tree()
        if len(mem_parts) == 1 or mem_parts[1] == "list":
            memories = _store.list_all()
            if memories:
                for m in memories:
                    repl_print(f"  [{m['type']}] {m['name']} ({m['filename']})")
            else:
                repl_print("[dim]No memories saved.[/dim]")
        elif mem_parts[1] == "delete" and len(mem_parts) > 2:
            target = mem_parts[2]
            deleted = any(_store.delete(cat, target) for cat in VALID_CATEGORIES)
            if deleted:
                repl_print(f"[dim]Deleted {target}[/dim]")
            else:
                repl_print(f"[yellow]Memory not found: {target}[/yellow]")
        return "continue"

    if cmd == "/vchange":
        step = None
        if args:
            try:
                step = int(args.strip())
            except ValueError:
                repl_print("[red]Usage: /vchange [-N|N]  (e.g. /vchange -1)[/red]")
                return "continue"
        # run_vchange lives in cli.py; import here to avoid circular dependency
        from ohmycode import cli as _cli_module
        _cli_module.run_vchange(step)
        return "continue"

    if cmd == "/think":
        arg = args.strip().lower()
        valid = ("low", "medium", "high", "off")
        if not arg:
            state = conv.think or "off"
            repl_print(f"[dim]Thinking: {state}[/dim]")
        elif arg not in valid:
            repl_print("[red]Usage: /think low|medium|high|off[/red]")
        elif arg == "off":
            conv.think = None
            repl_print("[dim]Thinking disabled.[/dim]")
        else:
            conv.think = arg
            repl_print(f"[dim]Thinking set to: {arg}[/dim]")
        return "continue"

    if cmd == "/skills":
        if skills:
            repl_print("\n  [bold]Available skills:[/]")
            max_name = max(len(s) for s in skills) + 1
            for skill_name, info in sorted(skills.items()):
                padded = f"/{skill_name}".ljust(max_name + 1)
                desc = info.description
                if len(desc) > 60:
                    desc = desc[:57] + "..."
                repl_print(f"    [cyan]{padded}[/] [dim]{desc}[/]")
            repl_print()
        else:
            repl_print("[dim]No skills found.[/dim]")
        return "continue"

    # Skill dispatch or unknown command
    skill_name = cmd.lstrip("/")
    if skill_name in skills:
        skill_content = load_skill(skills[skill_name], arguments=args)
        conv.add_user_message(skill_content)
        finish_reason = await stream_fn(conv)
        if finish_reason == "max_turns":
            repl_print("[yellow]Reached maximum turns limit.[/yellow]")
        elif finish_reason == "cancelled":
            repl_print("\n[yellow](Interrupted — partial reply saved to history. Continue or /exit)[/yellow]")
    else:
        repl_print(f"[red]Unknown command: {cmd}[/red]")
        repl_print("[dim]Available: /exit /clear /new /mode /status /memory /skills[/dim]")
    return "continue"
