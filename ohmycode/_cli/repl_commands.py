"""REPL slash command handlers."""

from __future__ import annotations

import os
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Callable

# Re-imported here so callers don't need a separate import for confirm_tool_call
from ohmycode._cli.output import (
    ACCENT,  # noqa: F401 (used by callers via this module)
    MemoryBox,
)
from ohmycode.config.config import OhMyCodeConfig, load_config
from ohmycode.context.runtime import ContextRuntime
from ohmycode.core.loop import ConversationLoop
from ohmycode.memory.memory import (
    VALID_CATEGORIES,
    BTreeMemoryStore,
    extract_memories_with_box_cancellable,
    get_project_memory_dir,
)
from ohmycode.skills.loader import SkillInfo, load_skill
from ohmycode.storage.conversation import (
    list_unextracted_conversations,
    load_conversation,
    mark_conversation_memories_extracted,
    save_conversation,
)


@dataclass
class SlashCtx:
    """Per-invocation state passed to each slash-command handler."""

    cmd: str
    raw_input: str
    conv: ConversationLoop
    config: OhMyCodeConfig
    config_overrides: dict[str, Any]
    skills: dict[str, SkillInfo]
    resumed_filename: str | None
    session_id: str
    repl_print: Callable
    repl_print_plain: Callable
    stream_fn: Callable
    confirm_tool_call: Callable
    get_current_mode: Callable[[], str]
    set_current_mode: Callable[[str], None]
    set_conv: Callable[[ConversationLoop], None]
    set_config: Callable[[OhMyCodeConfig], None]
    set_resumed_filename: Callable[[str | None], None]
    cancel_event: Any
    context_runtime: ContextRuntime | None
    schedule_context_curator: Callable[[], None] | None


Handler = Callable[[SlashCtx, str], Awaitable["str | int"]]


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
    cancel_event: Any = None,
    context_runtime: ContextRuntime | None = None,
    schedule_context_curator: Callable[[], None] | None = None,
) -> str | int:
    """Dispatch a slash command. Returns 'continue', 'break', or an int exit code."""
    args = parts[1] if len(parts) > 1 else ""
    ctx = SlashCtx(
        cmd=cmd,
        raw_input=raw_input,
        conv=conv,
        config=config,
        config_overrides=config_overrides,
        skills=skills,
        resumed_filename=resumed_filename,
        session_id=session_id,
        repl_print=repl_print,
        repl_print_plain=repl_print_plain,
        stream_fn=stream_fn,
        confirm_tool_call=confirm_tool_call,
        get_current_mode=get_current_mode,
        set_current_mode=set_current_mode,
        set_conv=set_conv,
        set_config=set_config,
        set_resumed_filename=set_resumed_filename,
        cancel_event=cancel_event,
        context_runtime=context_runtime,
        schedule_context_curator=schedule_context_curator,
    )

    # /memory uses a substring match (multi-token args), so it routes first.
    if raw_input.startswith("/memory"):
        return await _handle_memory(ctx, args)

    handler = _COMMAND_HANDLERS.get(cmd)
    if handler is not None:
        return await handler(ctx, args)

    return await _handle_skill_or_unknown(ctx, args)


# ── Per-command handlers ─────────────────────────────────────────────────────


async def _handle_exit(ctx: SlashCtx, args: str) -> str | int:
    ctx.repl_print_plain("Goodbye.")
    if ctx.conv.messages:
        save_conversation(
            ctx.conv.messages, ctx.config.provider, ctx.config.model, ctx.config.mode,
            filename=ctx.resumed_filename,
            session_id=ctx.session_id,
            memories_extracted=False,
        )
        ctx.repl_print_plain("Conversation saved.")
    if ctx.conv.is_ready:
        await _extract_pending_memories(ctx)
    return 0


async def _extract_pending_memories(ctx: SlashCtx) -> None:
    pending = list_unextracted_conversations(ctx.session_id)
    if not pending:
        return
    n = len(pending)
    ctx.repl_print_plain(
        f"  Extracting memories from {n} conversation{'s' if n > 1 else ''}..."
    )
    store = BTreeMemoryStore(get_project_memory_dir(os.getcwd()))
    store.ensure_tree()
    if ctx.cancel_event is not None:
        ctx.cancel_event.clear()
    for i, filename in enumerate(pending, 1):
        result = load_conversation(filename)
        if result is None:
            mark_conversation_memories_extracted(filename)
            continue
        msgs, _ = result
        box = MemoryBox()
        try:
            memories, cancelled = await extract_memories_with_box_cancellable(
                msgs, ctx.conv.provider, ctx.config.model, box, ctx.cancel_event
            )
        except Exception:
            memories, cancelled = [], False
        box.clear()
        if cancelled:
            skipped = n - (i - 1)
            ctx.repl_print_plain(
                f"  Memory extraction cancelled — {skipped} conversation"
                f"{'s' if skipped != 1 else ''} skipped"
            )
            break
        for m in memories:
            store.save(m["name"], m["type"], m["content"])
        mark_conversation_memories_extracted(filename)
        count = len(memories)
        ctx.repl_print_plain(
            f"  ✓ Conversation {i} ({count} memor{'y' if count == 1 else 'ies'} saved)"
        )
    if ctx.cancel_event is not None:
        ctx.cancel_event.clear()


async def _handle_clear(ctx: SlashCtx, args: str) -> str:
    ctx.conv.messages.clear()
    ctx.conv.auto_approved.clear()
    ctx.repl_print("[dim]Conversation cleared.[/dim]")
    return "continue"


async def _handle_new(ctx: SlashCtx, args: str) -> str:
    if ctx.conv.messages:
        try:
            saved = save_conversation(
                ctx.conv.messages, ctx.config.provider, ctx.config.model, ctx.config.mode,
                session_id=ctx.session_id,
                memories_extracted=False,
            )
            ctx.repl_print(f"[dim]Conversation saved: {saved}[/dim]")
        except Exception as e:
            ctx.repl_print(f"[red]Failed to save conversation: {e}[/red]")
            ctx.repl_print("[dim]Conversation not reset. Fix the error and try again.[/dim]")
            return "continue"
    if ctx.context_runtime is not None:
        ctx.conv.messages.clear()
        ctx.conv.auto_approved.clear()
        ctx.set_resumed_filename(None)
        ctx.repl_print("[dim]New short-term conversation started. Long-term context kept.[/dim]")
        return "continue"
    new_conv = ConversationLoop(config=ctx.config, confirm_fn=ctx.confirm_tool_call)
    new_conv.initialize()
    ctx.set_conv(new_conv)
    ctx.set_resumed_filename(None)
    ctx.repl_print("[dim]New conversation started.[/dim]")
    return "continue"


async def _handle_mode(ctx: SlashCtx, args: str) -> str:
    if not args:
        ctx.repl_print(f"[dim]Current mode: {ctx.get_current_mode()}[/dim]")
        ctx.repl_print("[dim]Usage: /mode <default|auto|plan>[/dim]")
        return "continue"
    new_mode = args.strip()
    if new_mode not in ("default", "auto", "plan"):
        ctx.repl_print(f"[red]Unknown mode: {new_mode}[/red]")
        return "continue"
    ctx.set_current_mode(new_mode)
    new_overrides = dict(ctx.config_overrides)
    new_overrides["mode"] = new_mode
    new_config = load_config(new_overrides)
    new_conv = ConversationLoop(config=new_config, confirm_fn=ctx.confirm_tool_call)
    new_conv.initialize()
    ctx.set_config(new_config)
    ctx.set_conv(new_conv)
    ctx.repl_print(f"[dim]Mode switched to: {new_mode}[/dim]")
    return "continue"


async def _handle_model(ctx: SlashCtx, args: str) -> str:
    profile_name = args.strip()
    if not profile_name:
        _print_model_profiles(ctx.config, ctx.config_overrides, ctx.repl_print)
        return "continue"

    new_overrides = _profile_switch_overrides(
        ctx.config_overrides, profile_name, ctx.get_current_mode()
    )
    try:
        new_config = load_config(new_overrides)
    except ValueError as exc:
        ctx.repl_print(f"[red]{exc}[/red]")
        return "continue"
    new_conv = ConversationLoop(config=new_config, confirm_fn=ctx.confirm_tool_call)
    new_conv.initialize()
    ctx.config_overrides.clear()
    ctx.config_overrides.update(new_overrides)
    ctx.set_current_mode(new_config.mode)
    ctx.set_config(new_config)
    ctx.set_conv(new_conv)
    ctx.repl_print(
        f"[dim]Model profile switched to {profile_name}: "
        f"{new_config.provider} / {new_config.model}[/dim]"
    )
    return "continue"


async def _handle_status(ctx: SlashCtx, args: str) -> str:
    status = ctx.conv.get_status_snapshot()
    ctx.repl_print()
    ctx.repl_print("  [bold]Session status[/]")
    ctx.repl_print(
        f"    [dim]Model:[/] {status['provider']} / {status['model']}    "
        f"[dim]Mode:[/] {status['mode']}"
    )
    ctx.repl_print(
        f"    [dim]Messages:[/] {status['message_count']}    "
        f"[dim]Context:[/] {status['used_tokens']:,} / {status['effective_window']:,} tokens "
        f"([bold]{status['usage_percent']:.1f}%[/])"
    )
    ctx.repl_print(
        f"    [dim]Budget:[/] {status['token_budget']:,} total, "
        f"{status['output_reserved']:,} reserved for output"
    )
    ctx.repl_print(f"    [dim]Compression stage:[/] {status['compression_stage']}")
    ctx.repl_print()
    return "continue"


async def _handle_context(ctx: SlashCtx, args: str) -> str:
    return _handle_context_command(
        args,
        ctx.context_runtime,
        ctx.repl_print,
        ctx.schedule_context_curator,
    )


async def _handle_memory(ctx: SlashCtx, args: str) -> str:
    mem_parts = ctx.raw_input.split(maxsplit=2)
    store = BTreeMemoryStore(get_project_memory_dir(os.getcwd()))
    store.ensure_tree()
    if len(mem_parts) == 1 or mem_parts[1] == "list":
        memories = store.list_all()
        if memories:
            for m in memories:
                ctx.repl_print(f"  [{m['type']}] {m['name']} ({m['filename']})")
        else:
            ctx.repl_print("[dim]No memories saved.[/dim]")
    elif mem_parts[1] == "delete" and len(mem_parts) > 2:
        target = mem_parts[2]
        deleted = any(store.delete(cat, target) for cat in VALID_CATEGORIES)
        if deleted:
            ctx.repl_print(f"[dim]Deleted {target}[/dim]")
        else:
            ctx.repl_print(f"[yellow]Memory not found: {target}[/yellow]")
    return "continue"


async def _handle_vchange(ctx: SlashCtx, args: str) -> str:
    step = None
    if args:
        try:
            step = int(args.strip())
        except ValueError:
            ctx.repl_print("[red]Usage: /vchange [-N|N]  (e.g. /vchange -1)[/red]")
            return "continue"
    from ohmycode.commands.vchange import run_vchange
    run_vchange(step)
    return "continue"


async def _handle_think(ctx: SlashCtx, args: str) -> str:
    arg = args.strip().lower()
    valid = ("low", "medium", "high", "off")
    if not arg:
        state = ctx.conv.think or "off"
        ctx.repl_print(f"[dim]Thinking: {state}[/dim]")
    elif arg not in valid:
        ctx.repl_print("[red]Usage: /think low|medium|high|off[/red]")
    elif arg == "off":
        ctx.conv.think = None
        ctx.repl_print("[dim]Thinking disabled.[/dim]")
    else:
        ctx.conv.think = arg
        ctx.repl_print(f"[dim]Thinking set to: {arg}[/dim]")
    return "continue"


async def _handle_skills(ctx: SlashCtx, args: str) -> str:
    if ctx.skills:
        ctx.repl_print("\n  [bold]Available skills:[/]")
        max_name = max(len(s) for s in ctx.skills) + 1
        for skill_name, info in sorted(ctx.skills.items()):
            padded = f"/{skill_name}".ljust(max_name + 1)
            desc = info.description
            if len(desc) > 60:
                desc = desc[:57] + "..."
            ctx.repl_print(f"    [cyan]{padded}[/] [dim]{desc}[/]")
        ctx.repl_print()
    else:
        ctx.repl_print("[dim]No skills found.[/dim]")
    return "continue"


async def _handle_skill_or_unknown(ctx: SlashCtx, args: str) -> str:
    skill_name = ctx.cmd.lstrip("/")
    if skill_name in ctx.skills:
        skill_content = load_skill(ctx.skills[skill_name], arguments=args)
        ctx.conv.add_user_message(skill_content)
        finish_reason = await ctx.stream_fn(ctx.conv)
        if finish_reason == "max_turns":
            ctx.repl_print("[yellow]Reached maximum turns limit.[/yellow]")
        elif finish_reason == "cancelled":
            ctx.repl_print(
                "\n[yellow](Interrupted — partial reply saved to history. Continue or /exit)[/yellow]"
            )
    else:
        ctx.repl_print(f"[red]Unknown command: {ctx.cmd}[/red]")
        ctx.repl_print(
            "[dim]Available: /exit /clear /new /mode /model /status /context /memory /skills[/dim]"
        )
    return "continue"


_COMMAND_HANDLERS: dict[str, Handler] = {
    "/exit": _handle_exit,
    "/quit": _handle_exit,
    "/clear": _handle_clear,
    "/new": _handle_new,
    "/mode": _handle_mode,
    "/model": _handle_model,
    "/status": _handle_status,
    "/context": _handle_context,
    "/vchange": _handle_vchange,
    "/think": _handle_think,
    "/skills": _handle_skills,
}


# ── /model helpers ───────────────────────────────────────────────────────────


def _print_model_profiles(
    config: OhMyCodeConfig,
    config_overrides: dict[str, Any],
    repl_print: Callable,
) -> None:
    try:
        current = load_config(config_overrides)
    except ValueError:
        current = config
    repl_print()
    repl_print("  [bold]Model profiles[/]")
    if not current.profiles:
        repl_print("[dim]No profiles configured. Usage: /model <profile>[/dim]")
        repl_print()
        return
    active = current.active_profile
    for name, profile in sorted(current.profiles.items()):
        marker = "*" if name == active else " "
        provider = profile.get("provider", current.provider)
        model = profile.get("model", current.model)
        repl_print(f"    [cyan]{marker} {name}[/] [dim]{provider} / {model}[/]")
    repl_print()


def _profile_switch_overrides(
    config_overrides: dict[str, Any],
    profile_name: str,
    current_mode: str,
) -> dict[str, Any]:
    new_overrides = dict(config_overrides)
    for key in (
        "provider",
        "model",
        "api_key",
        "base_url",
        "auth_token",
        "azure_endpoint",
        "azure_api_version",
    ):
        new_overrides.pop(key, None)
    new_overrides["profile"] = profile_name
    if current_mode:
        new_overrides["mode"] = current_mode
    return new_overrides


# ── /context helper ──────────────────────────────────────────────────────────


def _handle_context_command(
    args: str,
    context_runtime: ContextRuntime | None,
    repl_print: Callable,
    schedule_context_curator: Callable[[], None] | None,
) -> str:
    if context_runtime is None:
        repl_print("[yellow]Long-term context is disabled.[/yellow]")
        return "continue"

    arg = args.strip()
    if not arg:
        packet = context_runtime.get_active_packet()
        active = packet.topic_id or "(none)"
        processed_event_id = context_runtime.store.get_last_processed_event_id()
        latest_event_id = context_runtime.store.get_max_event_id()
        curator_lag = max(0, latest_event_id - processed_event_id)
        repl_print()
        repl_print("  [bold]Long-term context[/]")
        repl_print(f"    [dim]Active topic:[/] {active}")
        repl_print(f"    [dim]Packet semantic version:[/] {packet.version}")
        repl_print(f"    [dim]Packet curated through event:[/] {packet.last_event_id}")
        repl_print(f"    [dim]Curator processed through event:[/] {processed_event_id}")
        repl_print(
            f"    [dim]Latest event:[/] {latest_event_id}    "
            f"[dim]Curator lag:[/] {curator_lag}"
        )
        repl_print(
            "    [dim]Curator:[/] "
            + ("running" if context_runtime.curator_running else "idle")
            + (" (pending)" if context_runtime.curator_pending else "")
        )
        if packet.title:
            repl_print(f"    [dim]Title:[/] {packet.title}")
        if packet.summary:
            repl_print(f"    [dim]Summary:[/] {packet.summary}")
        if packet.topic_id:
            cache = context_runtime.store.load_compression_cache(packet.topic_id)
            repl_print(
                f"    [dim]Slices:[/] {context_runtime.store.count_topic_slices(packet.topic_id)}    "
                f"[dim]Projected messages:[/] "
                f"{context_runtime.store.get_state('last_projection_message_count', '0')}"
            )
            if cache is not None:
                repl_print(
                    f"    [dim]Compressed until event:[/] {cache.compressed_until_event_id}    "
                    f"[dim]Raw tail:[/] "
                    f"{context_runtime.store.get_state('last_projection_raw_tail_count', '0')}"
                )
            else:
                repl_print("[dim]Compression cache:[/] none")
        repl_print()
        return "continue"

    if arg == "topics":
        topics = context_runtime.store.list_topics()
        if not topics:
            repl_print("[dim]No context topics yet.[/dim]")
            return "continue"
        repl_print("\n  [bold]Context topics[/]")
        for topic in topics:
            label = topic.title or topic.id
            slices = context_runtime.store.count_topic_slices(topic.id)
            cache = context_runtime.store.load_compression_cache(topic.id)
            cache_label = "compressed" if cache is not None else "raw"
            repl_print(
                f"    [cyan]{topic.id}[/] [dim]{label}[/] "
                f"[dim]slices={slices} {cache_label}[/]"
            )
        repl_print()
        return "continue"

    if arg.startswith("switch "):
        topic_id = arg.split(maxsplit=1)[1].strip()
        if context_runtime.switch_topic(topic_id):
            repl_print(f"[dim]Active context topic switched to {topic_id}.[/dim]")
        else:
            repl_print(f"[yellow]Unknown context topic: {topic_id}[/yellow]")
        return "continue"

    if arg == "rebuild":
        context_runtime.store.append_event(
            "context_correction", "Requested packet rebuild", {"action": "rebuild"}
        )
        context_runtime.store.set_state("packet_rebuild_requested", "1")
        if schedule_context_curator is not None:
            schedule_context_curator()
        repl_print("[dim]Context packet rebuild requested.[/dim]")
        return "continue"

    repl_print("[red]Usage: /context [topics|switch <topic_id>|rebuild][/red]")
    return "continue"
