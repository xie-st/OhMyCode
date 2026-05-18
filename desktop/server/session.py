import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any

from desktop.server._serialize import serialize_event
from desktop.server.growth_prompt import GROWTH_AGENT_PROMPT
from desktop.server.profile import UserProfile
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.events import EventBus
from ohmycode.core.loop import ConversationLoop
from ohmycode.core.messages import (
    StreamEvent,
    TextChunk,
    ToolCallResult,
    ToolCallStart,
    TurnComplete,
)


WsSend = Callable[[dict[str, Any]], Awaitable[None] | None]
B_TOOL_TRIGGER_DELAY_SECONDS = 3.0
B_COOLDOWN_SECONDS = 60.0
B_RATE_LIMIT_WINDOW_SECONDS = 600.0
B_RATE_LIMIT_MAX_TRIGGERS = 5
PERMISSION_TIMEOUT_SECONDS = 30.0


def _pick_b_model(config: OhMyCodeConfig) -> str:
    """Pick a smaller model for Window B when the provider is known."""
    if config.provider == "anthropic":
        return "claude-haiku-4-5-20251001"
    if config.provider == "openai":
        return "gpt-4o-mini"
    return config.model


class DesktopSession:
    """Desktop session with task Window A and coaching Window B."""

    def __init__(self, config: OhMyCodeConfig, ws_send: WsSend) -> None:
        self.config = config
        self._ws_send = ws_send
        self.profile = UserProfile.for_cwd(os.getcwd())
        self._pending_perms: dict[str, asyncio.Future[str]] = {}
        self._auto_approved_tools: set[str] = set()

        self.bus_a = EventBus()
        self.bus_a.subscribe(self._on_event_a)

        self.loop_a = ConversationLoop(config=config, confirm_fn=self._make_confirm_fn("A"))
        self.loop_a.initialize()
        self.loop_a.set_event_bus(self.bus_a)

        b_config = config.model_copy(
            update={
                "system_prompt_append": (
                    (config.system_prompt_append or "")
                    + "\n\n"
                    + GROWTH_AGENT_PROMPT
                ),
                "model": _pick_b_model(config),
            }
        )
        self.bus_b = EventBus()
        self.bus_b.subscribe(self._on_event_b)

        self.loop_b = ConversationLoop(config=b_config, confirm_fn=self._make_confirm_fn("B"))
        self.loop_b.initialize()
        self.loop_b.set_event_bus(self.bus_b)

        self._turn_task: asyncio.Task | None = None
        self._b_turn_task: asyncio.Task | None = None
        self._b_lock = asyncio.Lock()
        self._b_last_trigger_at: float = 0.0
        self._b_trigger_times: list[float] = []
        self._b_muted: bool = False
        self._pending_tool_triggers: set[str] = set()
        self._a_error_history: list[str] = []
        self._a_last_text: str = ""
        self._background_tasks: set[asyncio.Task] = set()

    async def _send(self, payload: dict[str, Any]) -> None:
        result = self._ws_send(payload)
        if isawaitable(result):
            await result

    def _make_confirm_fn(self, window_id: str) -> Callable[[str, dict], Awaitable[str]]:
        async def confirm(tool_name: str, params: dict) -> str:
            if tool_name in self._auto_approved_tools:
                return "y"

            request_id = uuid.uuid4().hex
            fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            self._pending_perms[request_id] = fut
            await self._send(
                {
                    "type": "permission_request",
                    "data": {
                        "request_id": request_id,
                        "window": window_id,
                        "tool_name": tool_name,
                        "params": params,
                    },
                }
            )

            try:
                answer = await asyncio.wait_for(fut, timeout=PERMISSION_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                answer = "n"
            finally:
                self._pending_perms.pop(request_id, None)

            if answer == "a":
                self._auto_approved_tools.add(tool_name)
            return answer

        return confirm

    def resolve_permission(self, request_id: str, answer: str) -> bool:
        fut = self._pending_perms.get(request_id)
        if fut is None or fut.done():
            return False
        fut.set_result(answer.strip().lower())
        return True

    async def _on_event_a(self, event: StreamEvent) -> None:
        self.profile.observe_event(event, "A")
        await self._send(serialize_event(event))
        if isinstance(event, ToolCallStart):
            # Add to pending set synchronously here so a fast ToolCallResult
            # arriving before the delayed task starts can still discard it.
            self._pending_tool_triggers.add(event.tool_use_id)
            self._track_background_task(
                self._delayed_tool_trigger(event.tool_use_id, "tool_executing")
            )
        elif isinstance(event, ToolCallResult):
            self._pending_tool_triggers.discard(event.tool_use_id)
            if event.is_error:
                self._a_error_history.append(event.result[:200])
                self._a_error_history = self._a_error_history[-5:]
                if (
                    len(self._a_error_history) >= 2
                    and self._a_error_history[-1] == self._a_error_history[-2]
                ):
                    self._schedule_b_trigger("repeated_error")
        elif isinstance(event, TextChunk):
            self._a_last_text = f"{self._a_last_text}{event.text}"[-4000:]
        elif isinstance(event, TurnComplete):
            self._schedule_b_trigger("turn_complete")

    async def _on_event_b(self, event: StreamEvent) -> None:
        await self._send_with_window(event, "B")

    async def _send_with_window(self, event: StreamEvent, window: str) -> None:
        payload = serialize_event(event)
        payload["window"] = window
        await self._send(payload)

    def _schedule_b_trigger(self, reason: str) -> None:
        self._track_background_task(self._maybe_trigger_b(reason))

    def _track_background_task(self, coro: Awaitable[None]) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _delayed_tool_trigger(self, tool_use_id: str, reason: str) -> None:
        await asyncio.sleep(B_TOOL_TRIGGER_DELAY_SECONDS)
        if tool_use_id in self._pending_tool_triggers:
            self._pending_tool_triggers.discard(tool_use_id)
            await self._maybe_trigger_b(reason)

    def set_b_muted(self, muted: bool) -> None:
        self._b_muted = muted

    def _b_trigger_allowed(self, now: float) -> bool:
        if (now - self._b_last_trigger_at) < B_COOLDOWN_SECONDS:
            return False
        if self._b_muted:
            return False
        self._b_trigger_times = [
            t
            for t in self._b_trigger_times
            if (now - t) < B_RATE_LIMIT_WINDOW_SECONDS
        ]
        return len(self._b_trigger_times) < B_RATE_LIMIT_MAX_TRIGGERS

    async def _maybe_trigger_b(self, reason: str) -> None:
        if self._b_lock.locked():
            return
        now = asyncio.get_event_loop().time()
        if not self._b_trigger_allowed(now):
            return
        async with self._b_lock:
            now = asyncio.get_event_loop().time()
            if not self._b_trigger_allowed(now):
                return
            self._b_last_trigger_at = now
            self._b_trigger_times.append(now)
            self._b_turn_task = asyncio.current_task()
            snapshot = self.profile.snapshot_for_b(current_text=self._a_last_text)
            observation = (
                f"[Observation] Window A is running {reason}\n"
                f"[Profile] {snapshot}"
            )
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
        self.profile.observe_user_message(text)
        self._a_last_text = ""
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
        for task in list(self._background_tasks):
            await self._cancel_task(task)

    async def _cancel_task(self, task: asyncio.Task | None) -> None:
        if not task or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
