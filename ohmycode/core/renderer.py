"""``Renderer`` protocol + an event-dispatching base class.

Frontends (CLI, web, IDE, tests) implement this protocol to consume the
agent's ``StreamEvent`` stream without the kernel knowing about them.

``DispatchingRenderer`` provides the per-event-type method dispatch so
concrete renderers do not have to write the ``isinstance`` ladder.
Override the ``on_<event>`` hook for whichever events you care about and
ignore the rest.

``drive_renderer`` runs the lifecycle (``on_turn_start`` →
``on_event`` per yielded event → ``on_turn_end``) against an async
event source.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

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


@runtime_checkable
class Renderer(Protocol):
    async def on_event(self, event: StreamEvent) -> None: ...


class DispatchingRenderer:
    """Base class that turns one ``on_event`` call into a per-type hook.

    Subclass and override ``on_text``, ``on_thinking``, ``on_tool_call_start``,
    ``on_tool_call_streaming``, ``on_tool_call_result``, ``on_sub_agent_tool_use``,
    ``on_sub_agent_done``, or ``on_turn_complete``. Anything you do not override
    is a no-op.

    For per-turn setup and teardown that does not belong to any specific
    event, override ``on_turn_start`` (called once before the first event)
    and ``on_turn_end`` (called once after the last, even on error).
    """

    # ── Lifecycle hooks ──────────────────────────────────────────────────────

    async def on_turn_start(self) -> None: ...
    async def on_turn_end(self) -> None: ...

    # ── Per-event dispatch ───────────────────────────────────────────────────

    async def on_event(self, event: StreamEvent) -> None:
        if isinstance(event, TextChunk):
            await self.on_text(event)
        elif isinstance(event, ThinkingChunk):
            await self.on_thinking(event)
        elif isinstance(event, ToolCallStreaming):
            await self.on_tool_call_streaming(event)
        elif isinstance(event, ToolCallStart):
            await self.on_tool_call_start(event)
        elif isinstance(event, ToolCallResult):
            await self.on_tool_call_result(event)
        elif isinstance(event, SubAgentToolUse):
            await self.on_sub_agent_tool_use(event)
        elif isinstance(event, SubAgentDone):
            await self.on_sub_agent_done(event)
        elif isinstance(event, TurnComplete):
            await self.on_turn_complete(event)

    # ── Hooks (no-op defaults) ───────────────────────────────────────────────

    async def on_text(self, event: TextChunk) -> None: ...
    async def on_thinking(self, event: ThinkingChunk) -> None: ...
    async def on_tool_call_streaming(self, event: ToolCallStreaming) -> None: ...
    async def on_tool_call_start(self, event: ToolCallStart) -> None: ...
    async def on_tool_call_result(self, event: ToolCallResult) -> None: ...
    async def on_sub_agent_tool_use(self, event: SubAgentToolUse) -> None: ...
    async def on_sub_agent_done(self, event: SubAgentDone) -> None: ...
    async def on_turn_complete(self, event: TurnComplete) -> None: ...


async def drive_renderer(
    renderer: "DispatchingRenderer",
    events: AsyncIterator[StreamEvent],
) -> None:
    """Run the ``on_turn_start`` → ``on_event`` × N → ``on_turn_end`` lifecycle.

    ``on_turn_end`` is invoked even when the iterator raises so renderers
    can clean up spinners/boxes/cursor state.
    """
    await renderer.on_turn_start()
    try:
        async for event in events:
            await renderer.on_event(event)
    finally:
        await renderer.on_turn_end()
