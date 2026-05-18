import asyncio
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any

from desktop.server._serialize import serialize_event
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.events import EventBus
from ohmycode.core.loop import ConversationLoop
from ohmycode.core.messages import StreamEvent


WsSend = Callable[[dict[str, Any]], Awaitable[None] | None]


class DesktopSession:
    """Window A session: one ConversationLoop plus WebSocket event fan-out."""

    def __init__(self, config: OhMyCodeConfig, ws_send: WsSend) -> None:
        self.config = config
        self._ws_send = ws_send

        self.bus_a = EventBus()
        self.bus_a.subscribe(self._on_event_a)

        self.loop_a = ConversationLoop(config=config)
        self.loop_a.initialize()
        self.loop_a.set_event_bus(self.bus_a)

        self._turn_task: asyncio.Task | None = None

    async def _send(self, payload: dict[str, Any]) -> None:
        result = self._ws_send(payload)
        if isawaitable(result):
            await result

    async def _on_event_a(self, event: StreamEvent) -> None:
        await self._send(serialize_event(event))

    async def handle_user_input(self, text: str) -> None:
        """Append user text and start a Window A turn if one is not active."""
        if self._turn_task and not self._turn_task.done():
            return
        self.loop_a.add_user_message(text)
        self._turn_task = asyncio.create_task(self._run_turn())

    async def _run_turn(self) -> None:
        try:
            async for _ in self.loop_a.stream_turn():
                pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._send({"type": "error", "data": {"message": str(exc)}})

    async def cancel(self) -> None:
        if not self._turn_task or self._turn_task.done():
            return
        self._turn_task.cancel()
        try:
            await self._turn_task
        except asyncio.CancelledError:
            pass
