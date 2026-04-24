"""Stream rendering: ThinkingBox and render_stream."""

from __future__ import annotations

import asyncio
import json
import sys
import time

from rich.console import Console
from rich.markup import escape

from ohmycode.core.loop import ConversationLoop
from ohmycode.core.messages import (
    TextChunk,
    ThinkingChunk,
    ToolCallStart,
    ToolCallResult,
    TurnComplete,
)

console = Console()

ACCENT = "#ff6b9d"

_BOX_CONTENT_WIDTH = 60
_BOX_LINES = 3
_BOX_THROTTLE = 0.05


class ThinkingBox:
    """Fixed-height scrolling box for streaming thinking content.

    All output goes through sys.stdout directly (no Rich) so that Rich's
    internal state stays clean for the text response that follows.
    """

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
        header = f"  \033[38;2;255;107;157m▌\033[0m \033[2mThinking\033[0m"
        rows = [header]
        for i in range(_BOX_LINES):
            if i < len(display):
                content = display[i][:_BOX_CONTENT_WIDTH]
                rows.append(f"  \033[2m│  {content}\033[0m")
            else:
                rows.append(f"  \033[2m│\033[0m")
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


class MemoryBox:
    """Fixed-height scrolling box for streaming memory extraction output.

    Identical mechanics to ThinkingBox but with an 'Analyzing' header,
    used during /exit to show live LLM output while extracting memories.
    """

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
        header = f"  \033[38;2;255;107;157m▌\033[0m \033[2mAnalyzing\033[0m"
        rows = [header]
        for i in range(_BOX_LINES):
            if i < len(display):
                content = display[i][:_BOX_CONTENT_WIDTH]
                rows.append(f"  \033[2m│  {content}\033[0m")
            else:
                rows.append(f"  \033[2m│\033[0m")
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


async def render_stream(conv: ConversationLoop) -> str:
    """Consume run_turn() event stream, render to terminal, return finish_reason."""
    finish_reason = "stop"
    text_printed = False
    tool_count = 0

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    thinking = True
    t_start = time.monotonic()
    spinner_task = None

    async def _spinner():
        idx = 0
        try:
            while True:
                elapsed = time.monotonic() - t_start
                frame = SPINNER_FRAMES[idx % len(SPINNER_FRAMES)]
                sys.stdout.write(f"\r  \033[2m{frame} Waiting... {elapsed:.0f}s\033[0m\033[K")
                sys.stdout.flush()
                idx += 1
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    spinner_task = asyncio.create_task(_spinner())
    box = ThinkingBox()

    try:
        async for event in conv.run_turn():
            if thinking:
                thinking = False
                if spinner_task and not spinner_task.done():
                    spinner_task.cancel()
                    try:
                        await spinner_task
                    except asyncio.CancelledError:
                        pass
                if conv.think:
                    sys.stdout.write("\n")
                    sys.stdout.flush()

            if isinstance(event, ThinkingChunk):
                if conv.think:
                    box.push(event.text)
                continue

            if isinstance(event, TextChunk):
                if box.visible:
                    box.clear()
                text = event.text
                if not text_printed:
                    if tool_count > 0:
                        console.print(f"\n  [bold {ACCENT}]●[/] ", end="", highlight=False)
                    else:
                        console.print("  ", end="", highlight=False)
                text = text.replace("\n", "\n    ")
                console.print(text, end="", highlight=False)
                text_printed = True

            elif isinstance(event, ToolCallStart):
                if box.visible:
                    box.clear()
                if text_printed:
                    console.print()
                    text_printed = False
                tool_display = event.tool_name
                params_str = json.dumps(event.params, ensure_ascii=False)
                if len(params_str) > 100:
                    params_str = params_str[:97] + "..."
                console.print(
                    f"\n    [bold {ACCENT}]▸[/] [bold]{escape(tool_display)}[/]  [dim]{escape(params_str)}[/]",
                    highlight=False,
                )
                tool_count += 1

            elif isinstance(event, ToolCallResult):
                raw = event.result
                max_lines = 10
                lines = raw.splitlines()
                if len(lines) > max_lines:
                    indented = "\n".join("    " + l for l in lines[:max_lines])
                    output = escape(indented) + f"\n    [dim]... ({len(lines)} lines total)[/dim]"
                else:
                    body = raw
                    if len(body) > 500:
                        body = body[:497] + "..."
                    body = "\n".join("    " + l for l in body.splitlines())
                    output = escape(body)

                if event.is_error:
                    console.print(f"    [red]✗[/] [red]{output}[/]", highlight=False)
                else:
                    console.print(f"    [green]✓[/]\n[dim]{output}[/]", highlight=False)

            elif isinstance(event, TurnComplete):
                finish_reason = event.finish_reason
                if box.visible:
                    box.clear()
                if text_printed:
                    console.print()
                    text_printed = False
                u = event.usage
                elapsed = time.monotonic() - t_start
                stats_parts = []
                if tool_count > 0:
                    stats_parts.append(f"{tool_count} tool use{'s' if tool_count > 1 else ''}")
                if u.total_tokens > 0:
                    stats_parts.append(f"{u.total_tokens:,} tokens")
                stats_parts.append(f"{elapsed:.1f}s")
                console.print(f"\n  [dim]{' · '.join(stats_parts)}[/dim]")
                tool_count = 0

    finally:
        if box.visible:
            box.clear()
        if spinner_task and not spinner_task.done():
            spinner_task.cancel()
            try:
                await spinner_task
            except asyncio.CancelledError:
                pass

    return finish_reason
