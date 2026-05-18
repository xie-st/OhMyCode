import asyncio
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any

from desktop.server._serialize import serialize_event
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.events import EventBus
from ohmycode.core.loop import ConversationLoop
from ohmycode.core.messages import StreamEvent, ToolCallStart


WsSend = Callable[[dict[str, Any]], Awaitable[None] | None]

B_PLACEHOLDER_PROMPT = (
    "You are a placeholder coaching agent. "
    "M2.1 only verifies the wiring; M2.2 replaces this with the real "
    "'小柚' persona prompt from growth_prompt.py."
)


def _pick_b_model(config: OhMyCodeConfig) -> str:
    """Pick a smaller model for Window B when the provider is known."""
    if config.provider == "anthropic":
        return "claude-haiku-4-5-20251001"
    if config.provider == "openai":
        return "gpt-4o-mini"
    return config.model


class DesktopSession:
    """Desktop session with task Window A and placeholder coaching Window B."""

    def __init__(self, config: OhMyCodeConfig, ws_send: WsSend) -> None:
        self.config = config
        self._ws_send = ws_send

        self.bus_a = EventBus()
        self.bus_a.subscribe(self._on_event_a)

        self.loop_a = ConversationLoop(config=config)
        self.loop_a.initialize()
        self.loop_a.set_event_bus(self.bus_a)

        b_config = config.model_copy(
            update={
                "system_prompt_append": (
                    (config.system_prompt_append or "")
                    + "\n\n"
                    + B_PLACEHOLDER_PROMPT
                ),
                "model": _pick_b_model(config),
            }
        )
        self.bus_b = EventBus()
        self.bus_b.subscribe(self._on_event_b)

        self.loop_b = ConversationLoop(config=b_config)
        self.loop_b.initialize()
        self.loop_b.set_event_bus(self.bus_b)

        self._turn_task: asyncio.Task | None = None
        self._b_turn_task: asyncio.Task | None = None
        self._b_lock = asyncio.Lock()

    async def _send(self, payload: dict[str, Any]) -> None:
        result = self._ws_send(payload)
        if isawaitable(result):
            await result

    async def _on_event_a(self, event: StreamEvent) -> None:
        await self._send(serialize_event(event))
        if isinstance(event, ToolCallStart):
            self._schedule_b_trigger("tool_executing")

    async def _on_event_b(self, event: StreamEvent) -> None:
        await self._send_with_window(event, "B")

    async def _send_with_window(self, event: StreamEvent, window: str) -> None:
        payload = serialize_event(event)
        payload["window"] = window
        await self._send(payload)

    def _schedule_b_trigger(self, reason: str) -> None:
        if self._b_turn_task and not self._b_turn_task.done():
            return
        self._b_turn_task = asyncio.create_task(self._maybe_trigger_b(reason))

    async def _maybe_trigger_b(self, reason: str) -> None:
        if self._b_lock.locked():
            return
        async with self._b_lock:
            observation = f"[观察] 主窗口正在执行 {reason}"
            self.loop_b.add_user_message(observation)
            try:
                async for _ in self.loop_b.stream_turn():
                    pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._send(
                    {"type": "error", "window": "B", "data": {"message": str(exc)}}
                )

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
        await self._cancel_task(self._turn_task)
        await self._cancel_task(self._b_turn_task)

    async def _cancel_task(self, task: asyncio.Task | None) -> None:
        if not task or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
