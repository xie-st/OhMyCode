"""Stream rendering: ScrollingBox family and the Rich-backed renderer."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time

from rich.console import Console
from rich.markup import escape

from ohmycode.core.loop import ConversationLoop
from ohmycode.core.messages import (
    StreamEvent,
    SubAgentDone,
    SubAgentToolUse,
    TextChunk,
    ThinkingChunk,
    ToolCallResult,
    ToolCallStart,
    ToolCallStreaming,
    TurnComplete,
)
from ohmycode.core.renderer import DispatchingRenderer, drive_renderer

console = Console()

ACCENT = "#ff6b9d"

_BOX_CONTENT_WIDTH = 60
_BOX_LINES = 3
_BOX_THROTTLE = 0.05
_ACCENT_ESC = "\033[38;2;255;107;157m"
_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


async def _spinner_task(message: str, t_start: float) -> None:
    idx = 0
    try:
        while True:
            elapsed = time.monotonic() - t_start
            frame = _SPINNER_FRAMES[idx % len(_SPINNER_FRAMES)]
            sys.stdout.write(f"\r  \033[2m{frame} {message} {elapsed:.0f}s\033[0m\033[K")
            sys.stdout.flush()
            idx += 1
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


async def _cancel_spinner(task: asyncio.Task | None) -> None:
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _is_interactive() -> bool:
    """Return True only when stdout is a real terminal that supports ANSI."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


class ScrollingBox:
    """Fixed-height scrolling box for live terminal feedback.

    All output goes through sys.stdout directly (no Rich) so that Rich's
    internal state stays clean for the text response that follows.
    Subclasses set the class-level ``_header`` string.
    """

    _header: str = ""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._current: str = ""
        self.visible: bool = False
        self._last_draw: float = 0.0
        self._drawn_height: int = 0

    def push(self, text: str) -> None:
        self._current += text
        while "\n" in self._current:
            head, self._current = self._current.split("\n", 1)
            self._flush_line(head)
        while len(self._current) >= _BOX_CONTENT_WIDTH:
            self._flush_line(self._current[:_BOX_CONTENT_WIDTH])
            self._current = self._current[_BOX_CONTENT_WIDTH:]
        now = time.monotonic()
        if now - self._last_draw >= _BOX_THROTTLE:
            self._draw()
            self._last_draw = now

    def _flush_line(self, line: str) -> None:
        if len(self._lines) >= _BOX_LINES:
            self._lines = []
        self._lines.append(line)

    def _build_frame(self) -> str:
        display = list(self._lines)
        if self._current:
            display = display + [self._current]
        display = display[-_BOX_LINES:]
        rows = [self._header]
        for i in range(_BOX_LINES):
            if i < len(display):
                content = display[i][:_BOX_CONTENT_WIDTH]
                rows.append(f"  \033[2m│  {content}\033[0m")
            else:
                rows.append("  \033[2m│\033[0m")
        return "\n".join(rows)

    def _draw(self) -> None:
        frame = self._build_frame()
        line_count = frame.count("\n") + 1
        if self.visible and self._drawn_height > 0:
            sys.stdout.write(f"\033[{self._drawn_height}A\033[J")
        sys.stdout.write(frame)
        sys.stdout.write("\n")
        sys.stdout.flush()
        self.visible = True
        self._drawn_height = line_count

    def clear(self) -> None:
        """Erase the box so normal output can follow."""
        self._draw()  # flush any pending content so _drawn_height is accurate
        if not self.visible:
            return
        sys.stdout.write(f"\033[{self._drawn_height}A\033[J")
        sys.stdout.flush()
        self.visible = False
        self._drawn_height = 0


class ThinkingBox(ScrollingBox):
    """Scrolling box for streaming extended-thinking output."""

    _header = f"  {_ACCENT_ESC}▌\033[0m \033[2mThinking\033[0m"


class MemoryBox(ScrollingBox):
    """Scrolling box used during /exit memory extraction."""

    _header = f"  {_ACCENT_ESC}▌\033[0m \033[2mAnalyzing\033[0m"


class SubAgentBox(ScrollingBox):
    """Scrolling box showing tool calls made inside a spawned sub-agent."""

    _header = f"\n  {_ACCENT_ESC}▌\033[0m \033[2mSub-agent\033[0m"

    def __init__(self) -> None:
        super().__init__()
        self._tool_count = 0
        self._start = time.monotonic()

    def push_tool(self, tool_name: str) -> None:
        """Record a tool-call event and redraw the box."""
        self._tool_count += 1
        self._flush_line(f"→ {tool_name}")
        now = time.monotonic()
        if now - self._last_draw >= _BOX_THROTTLE:
            self._draw()
            self._last_draw = now

    def finish(self) -> None:
        """Show a completion line, pause 0.6s, then clear."""
        elapsed = time.monotonic() - self._start
        n = self._tool_count
        label = f"tool{'s' if n != 1 else ''}"
        self._flush_line(f"✓ done ({n} {label}, {elapsed:.1f}s)")
        self._draw()
        time.sleep(0.6)
        self.clear()


class RichRenderer(DispatchingRenderer):
    """Rich/Console-backed renderer for the interactive REPL.

    Stateful: owns the spinner lifecycle, the thinking/sub-agent boxes,
    and the per-turn formatting context (was the last thing text? a
    tool? how many tools?). All scratch state is reset in
    ``on_turn_start`` so a single instance can drive multiple turns.
    """

    def __init__(self, conv: ConversationLoop) -> None:
        self.conv = conv
        self.finish_reason: str = "stop"
        self._t_start: float = 0.0
        self._spinner_task: asyncio.Task | None = None
        self._tool_spinner_task: asyncio.Task | None = None
        self._box: ThinkingBox | None = None
        self._sub_agent_box: SubAgentBox | None = None
        self._text_printed: bool = False
        self._tool_count: int = 0
        self._first_event_seen: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def on_turn_start(self) -> None:
        self.finish_reason = "stop"
        self._t_start = time.monotonic()
        self._spinner_task = asyncio.create_task(
            _spinner_task("Waiting...", self._t_start)
        )
        self._tool_spinner_task = None
        self._box = ThinkingBox()
        self._sub_agent_box = None
        self._text_printed = False
        self._tool_count = 0
        self._first_event_seen = False

    async def on_turn_end(self) -> None:
        if self._box is not None and self._box.visible:
            self._box.clear()
        await _cancel_spinner(self._spinner_task)
        await _cancel_spinner(self._tool_spinner_task)

    # ── First-event side effect ──────────────────────────────────────────────

    async def on_event(self, event: StreamEvent) -> None:
        if not self._first_event_seen:
            self._first_event_seen = True
            await _cancel_spinner(self._spinner_task)
            self._spinner_task = None
            if self.conv.think:
                sys.stdout.write("\n")
                sys.stdout.flush()
        await super().on_event(event)

    # ── Per-event hooks ──────────────────────────────────────────────────────

    async def on_sub_agent_tool_use(self, event: SubAgentToolUse) -> None:
        if not _is_interactive():
            return
        if self._sub_agent_box is None:
            self._sub_agent_box = SubAgentBox()
        self._sub_agent_box.push_tool(event.tool_name)

    async def on_sub_agent_done(self, event: SubAgentDone) -> None:
        if self._sub_agent_box is None:
            return
        if event.is_error:
            self._sub_agent_box.clear()
        else:
            self._sub_agent_box.finish()
        self._sub_agent_box = None

    async def on_tool_call_streaming(self, event: ToolCallStreaming) -> None:
        if self._tool_spinner_task is not None and not self._tool_spinner_task.done():
            return
        if self._text_printed:
            console.print()
            self._text_printed = False
        self._tool_spinner_task = asyncio.create_task(
            _spinner_task("Preparing...", time.monotonic())
        )

    async def on_thinking(self, event: ThinkingChunk) -> None:
        if self.conv.think and self._box is not None:
            self._box.push(event.text)

    async def on_text(self, event: TextChunk) -> None:
        if self._box is not None and self._box.visible:
            self._box.clear()
        text = event.text
        if not self._text_printed:
            if self._tool_count > 0:
                console.print(f"\n  [bold {ACCENT}]●[/] ", end="", highlight=False)
            else:
                console.print("  ", end="", highlight=False)
        text = text.replace("\n", "\n    ")
        console.print(text, end="", highlight=False)
        self._text_printed = True

    async def on_tool_call_start(self, event: ToolCallStart) -> None:
        await _cancel_spinner(self._tool_spinner_task)
        self._tool_spinner_task = None
        if self._box is not None and self._box.visible:
            self._box.clear()
        if self._text_printed:
            console.print()
            self._text_printed = False
        params_str = json.dumps(event.params, ensure_ascii=False)
        if len(params_str) > 100:
            params_str = params_str[:97] + "..."
        console.print(
            f"\n    [bold {ACCENT}]▸[/] [bold]{escape(event.tool_name)}[/]"
            f"  [dim]{escape(params_str)}[/]",
            highlight=False,
        )
        self._tool_count += 1

    async def on_tool_call_result(self, event: ToolCallResult) -> None:
        raw = event.result
        max_lines = 10
        lines = raw.splitlines()
        if len(lines) > max_lines:
            indented = "\n".join("    " + line for line in lines[:max_lines])
            output = escape(indented) + f"\n    [dim]... ({len(lines)} lines total)[/dim]"
        else:
            body = raw
            if len(body) > 500:
                body = body[:497] + "..."
            body = "\n".join("    " + line for line in body.splitlines())
            output = escape(body)

        if event.is_error:
            console.print(f"    [red]✗[/] [red]{output}[/]", highlight=False)
        else:
            console.print(f"    [green]✓[/]\n[dim]{output}[/]", highlight=False)

    async def on_turn_complete(self, event: TurnComplete) -> None:
        self.finish_reason = event.finish_reason
        if self._box is not None and self._box.visible:
            self._box.clear()
        if self._text_printed:
            console.print()
            self._text_printed = False
        u = event.usage
        elapsed = time.monotonic() - self._t_start
        stats_parts: list[str] = []
        if self._tool_count > 0:
            stats_parts.append(
                f"{self._tool_count} tool use{'s' if self._tool_count > 1 else ''}"
            )
        if u and u.total_tokens > 0:
            stats_parts.append(f"{u.total_tokens:,} tokens")
        stats_parts.append(f"{elapsed:.1f}s")
        console.print(f"\n  [dim]{' · '.join(stats_parts)}[/dim]")
        self._tool_count = 0


async def render_stream(
    conv: ConversationLoop,
    system_prompt_override: str | None = None,
    allow_blocking_compression: bool = True,
) -> str:
    """Drive a ``RichRenderer`` against ``conv.run_turn()`` and return finish_reason."""
    renderer = RichRenderer(conv)
    events = conv.run_turn(
        system_prompt_override=system_prompt_override,
        allow_blocking_compression=allow_blocking_compression,
    )
    await drive_renderer(renderer, events)
    return renderer.finish_reason
