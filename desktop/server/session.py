import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from pathlib import Path
from typing import Any

from desktop.server._message_serialize import deserialize_message, serialize_message
from desktop.server._serialize import serialize_event
from desktop.server.growth_prompt import GROWTH_AGENT_PROMPT
from desktop.server.profile import UserProfile
from desktop.server.render_rules import truncate_params, truncate_result
from desktop.server.sessions import Session, SessionStore, sessions_store
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.events import EventBus
from ohmycode.core.loop import ConversationLoop
from ohmycode.core.messages import (
    AssistantMessage,
    Message,
    StreamEvent,
    TextChunk,
    ToolCallResult,
    ToolResultMessage,
    TurnComplete,
    UserMessage,
)
from ohmycode.memory.backend import (
    _canonical_project_root,
    _find_git_root,
    _sanitize_slug,
)


WsSend = Callable[[dict[str, Any]], Awaitable[None] | None]
B_COOLDOWN_SECONDS = 60.0
B_RATE_LIMIT_WINDOW_SECONDS = 600.0
B_RATE_LIMIT_MAX_TRIGGERS = 5
PERMISSION_TIMEOUT_SECONDS = 30.0
B_SILENT_TOKENS = frozenset({"[silent]", "(silent)"})
WINDOWS_HINT = (
    "\n\nNote: You are running on Windows. The bash tool uses cmd.exe by default; "
    "prefer Windows commands (`dir`, `type`, `findstr`, `where`) over Unix commands "
    "(`ls`, `cat`, `grep`, `which`). If the user explicitly asks for Unix commands, "
    "use `powershell -Command` to invoke them."
)
UNTITLED_SESSION_TITLES = {"New conversation", "\u65b0\u4f1a\u8bdd"}


def _user_message_text(message: UserMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "\n".join(item for item in message.content if isinstance(item, str))


def _attach_tool_result(rows: list[dict], message: ToolResultMessage) -> None:
    for row in reversed(rows):
        if row.get("role") != "assistant":
            continue
        segments = row.get("segments")
        if not isinstance(segments, list):
            continue
        for segment in segments:
            if not isinstance(segment, dict) or segment.get("kind") != "tool":
                continue
            tool = segment.get("tool")
            if not isinstance(tool, dict) or tool.get("id") != message.tool_use_id:
                continue
            preview, is_truncated = truncate_result(message.content)
            tool["result"] = message.content
            tool["resultPreview"] = preview
            tool["isTruncated"] = is_truncated
            tool["isError"] = message.is_error
            return


def _derive_title(text: str) -> str:
    """Derive a compact title from the first user message."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= 30:
        return cleaned or "\u65b0\u4f1a\u8bdd"
    return cleaned[:30] + "\u2026"


def _pick_b_model(config: OhMyCodeConfig) -> str:
    """Pick model for Window B.

    Explicit ``window_b_model`` wins; otherwise mirror the main ``model``.

    The previous hardcode (``provider=='openai' -> gpt-4o-mini``) assumed
    ``provider`` named the vendor, but ``provider`` is a protocol family:
    DeepSeek/Moonshot/Azure all set ``provider='openai'`` plus a custom
    ``base_url`` and reject foreign model names. Sharing the main model is
    the only universally-safe default.
    """
    return config.window_b_model or config.model


class DesktopSession:
    """Desktop session with task Window A and coaching Window B."""

    def __init__(
        self,
        config: OhMyCodeConfig,
        ws_send: WsSend,
        session_id: str | None = None,
        store: SessionStore | None = None,
    ) -> None:
        self.config = config
        self._ws_send = ws_send
        self.profile = UserProfile.for_cwd(os.getcwd())
        self.project_slug = self._project_slug()
        self.store = store or sessions_store
        self.session = self._resolve_session(session_id)
        self._ensure_inspiration_dirs()
        self._pending_perms: dict[str, asyncio.Future[str]] = {}
        self._auto_approved_tools: set[str] = set()
        raw_messages_a: list[dict] = []
        raw_messages_b: list[dict] = []
        if self.session is not None:
            raw_messages_a = self.store.load_messages(
                self.project_slug, self.session.id, "A"
            )
            raw_messages_b = self.store.load_messages(
                self.project_slug, self.session.id, "B"
            )
        self.messages_a: list[dict] = []
        self.messages_b: list[dict] = []

        self.bus_a = EventBus()
        self.bus_a.subscribe(self._on_event_a)

        config_a = self._with_windows_hint(config)
        self.loop_a = ConversationLoop(config=config_a, confirm_fn=self._make_confirm_fn("A"))
        self.loop_a.initialize()
        self._load_loop_history(self.loop_a, raw_messages_a)
        self.messages_a = self._messages_to_frontend_view(self.loop_a.messages)
        self.loop_a.set_event_bus(self.bus_a)

        sessions_root = str(
            Path.home()
            / ".ohmycode"
            / "projects"
            / self.project_slug
            / "sessions"
        )
        inspirations = self.profile.load_inspirations()
        inspirations_section = (
            f"## Inspiration resources\n{inspirations}" if inspirations.strip() else ""
        )
        b_prompt = GROWTH_AGENT_PROMPT.replace(
            "{sessions_root}", sessions_root
        ).replace("{inspirations_section}", inspirations_section)
        b_config = config.model_copy(
            update={
                "system_prompt_append": (
                    (config.system_prompt_append or "")
                    + "\n\n"
                    + b_prompt
                ),
                "model": _pick_b_model(config),
            }
        )
        self.bus_b = EventBus()
        self.bus_b.subscribe(self._on_event_b)

        self.loop_b = ConversationLoop(config=b_config, confirm_fn=self._make_confirm_fn("B"))
        self.loop_b.initialize()
        self._load_loop_history(self.loop_b, raw_messages_b)
        self.messages_b = self._messages_to_frontend_view(self.loop_b.messages)
        self.loop_b.set_event_bus(self.bus_b)

        self._turn_task: asyncio.Task | None = None
        self._b_turn_task: asyncio.Task | None = None
        self._b_lock = asyncio.Lock()
        self._b_last_trigger_at: float = 0.0
        self._b_trigger_times: list[float] = []
        self._b_muted: bool = False
        self._a_error_history: list[str] = []
        self._a_last_text: str = ""
        self._b_pending_text: str = ""
        self._last_b_trigger_reason: str = ""
        self._background_tasks: set[asyncio.Task] = set()

    def _with_windows_hint(self, config: OhMyCodeConfig) -> OhMyCodeConfig:
        if os.name != "nt":
            return config
        return config.model_copy(
            update={
                "system_prompt_append": (
                    (config.system_prompt_append or "") + WINDOWS_HINT
                )
            }
        )

    def _project_slug(self) -> str:
        root = _canonical_project_root(_find_git_root(os.getcwd()) or os.getcwd())
        return _sanitize_slug(root)

    def _resolve_session(self, session_id: str | None) -> Session | None:
        if session_id:
            for session in self.store.list_sessions(self.project_slug):
                if session.id == session_id:
                    return session
        return None

    def current_session_payload(self) -> dict[str, str] | None:
        if self.session is None:
            return None
        return {
            "id": self.session.id,
            "title": self.session.title,
            "created_at": self.session.created_at,
            "updated_at": self.session.updated_at,
            "project_slug": self.session.project_slug,
        }

    def _load_loop_history(self, loop: ConversationLoop, messages: list[dict]) -> None:
        warned_legacy = False
        for item in messages:
            if not isinstance(item, dict):
                continue
            try:
                loop.messages.append(deserialize_message(item))
                continue
            except (KeyError, TypeError):
                pass

            role = item.get("role")
            text = item.get("text")
            if not isinstance(text, str):
                continue
            if not warned_legacy:
                print("Migrating legacy session format (tool sequences will be lost)")
                warned_legacy = True
            if role == "user":
                loop.messages.append(UserMessage(text))
            elif role == "assistant":
                loop.messages.append(AssistantMessage(text))

    def _messages_to_frontend_view(self, messages: list[Message]) -> list[dict]:
        rows: list[dict] = []
        for index, message in enumerate(messages):
            if isinstance(message, UserMessage):
                rows.append(
                    {
                        "id": f"history-{index}",
                        "role": "user",
                        "text": _user_message_text(message),
                    }
                )
            elif isinstance(message, AssistantMessage):
                segments = []
                if message.content:
                    segments.append({"kind": "text", "text": message.content})
                for tool_call in message.tool_calls:
                    segments.append(
                        {
                            "kind": "tool",
                            "tool": {
                                "id": tool_call.tool_use_id,
                                "name": tool_call.tool_name,
                                "params": tool_call.params,
                                "paramsPreview": truncate_params(tool_call.params),
                            },
                        }
                    )
                rows.append(
                    {
                        "id": f"history-{index}",
                        "role": "assistant",
                        "text": message.content,
                        "segments": segments,
                    }
                )
            elif isinstance(message, ToolResultMessage):
                _attach_tool_result(rows, message)
        return rows

    def _ensure_inspiration_dirs(self) -> None:
        project_root = Path.home() / ".ohmycode" / "projects" / self.project_slug
        (project_root / "inspirations").mkdir(parents=True, exist_ok=True)
        (Path.home() / ".ohmycode" / "inspirations").mkdir(parents=True, exist_ok=True)

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
                        "params_preview": truncate_params(params),
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
        if isinstance(event, ToolCallResult):
            if event.is_error:
                self._a_error_history.append(event.result[:200])
                self._a_error_history = self._a_error_history[-5:]
        elif isinstance(event, TextChunk):
            self._a_last_text = f"{self._a_last_text}{event.text}"[-4000:]
        elif isinstance(event, TurnComplete):
            self._schedule_b_trigger("turn_complete")
            self._persist_window("A")

    async def _on_event_b(self, event: StreamEvent) -> None:
        if isinstance(event, TextChunk):
            self._b_pending_text += event.text
            if self._b_silent_pending():
                return
            text = self._b_pending_text
            self._b_pending_text = ""
            await self._send_with_window(TextChunk(text), "B")
            return
        if isinstance(event, TurnComplete):
            text = self._b_pending_text.strip().lower()
            if text in B_SILENT_TOKENS:
                await self._send(
                    {
                        "type": "b_silent",
                        "window": "B",
                        "data": {
                            "reason": self._last_b_trigger_reason
                            or "turn_complete"
                        },
                    }
                )
                self._b_pending_text = ""
                self._persist_window("B")
                return
            if self._b_pending_text:
                await self._send_with_window(TextChunk(self._b_pending_text), "B")
                self._b_pending_text = ""
            await self._send_with_window(event, "B")
            self._persist_window("B")
            return
        if self._b_pending_text and self._b_silent_pending():
            return
        await self._send_with_window(event, "B")

    def _b_silent_pending(self) -> bool:
        head = self._b_pending_text.lstrip()[:9].lower()
        return head.startswith(("[", "(")) and len(self._b_pending_text) < 12

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

    def set_b_muted(self, muted: bool) -> None:
        self._b_muted = muted

    def save_messages(self, target: str, messages: list[dict]) -> None:
        print(
            "[save_session] ignored frontend view; "
            "kernel history is persisted on TurnComplete"
        )

    def _persist_window(self, window: str) -> None:
        if self.session is None:
            return
        loop = self.loop_b if window == "B" else self.loop_a
        serialized = [serialize_message(message) for message in loop.messages]
        self.store.save_messages(self.project_slug, self.session.id, window, serialized)
        view = self._messages_to_frontend_view(loop.messages)
        if window == "A":
            self.messages_a = view
        else:
            self.messages_b = view

    async def _ensure_committed(self, title_source: str) -> None:
        title = _derive_title(title_source)
        if self.session is None:
            self.session = self.store.create_new(self.project_slug, title=title)
            await self._send(
                {"type": "current_session", "data": self.current_session_payload()}
            )
            return
        if self.session.title in UNTITLED_SESSION_TITLES:
            self.store.update_title(self.project_slug, self.session.id, title)
            self.session.title = title
            await self._send(
                {"type": "current_session", "data": self.current_session_payload()}
            )

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
            self._last_b_trigger_reason = reason
            snapshot = self.profile.snapshot_for_b(current_text=self._a_last_text)
            observation = (
                f"[trigger_reason] {reason}\n"
                f"[profile_snapshot] {snapshot}\n"
                f"[window_a_context] {self._a_last_text[-2000:]}"
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

    async def handle_user_input(self, text: str, target: str = "A") -> None:
        """Append user text and start a turn in the selected window."""
        await self._ensure_committed(text)
        if target == "B":
            await self._run_explicit_b_turn(text)
            return

        if self._turn_task and not self._turn_task.done():
            return
        self.profile.observe_user_message(text)
        self._a_last_text = ""
        self.loop_a.add_user_message(text)
        self._schedule_b_trigger("user_input")
        self._turn_task = asyncio.create_task(self._run_turn())

    async def _run_explicit_b_turn(self, text: str) -> None:
        async with self._b_lock:
            self._last_b_trigger_reason = "user_explicit"
            self.loop_b.add_user_message(text)
            self._b_turn_task = asyncio.current_task()
            try:
                async for _ in self.loop_b.stream_turn():
                    pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._send(
                    {"type": "error", "window": "B", "data": {"message": str(exc)}}
                )
            finally:
                self._b_turn_task = None

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

    async def swap_to(self, session_id: str) -> None:
        """Switch persisted session history without rebuilding provider loops."""
        await self.cancel()
        self.session = self.store.load_session(self.project_slug, session_id)
        raw_messages_a: list[dict] = []
        raw_messages_b: list[dict] = []
        if self.session is None:
            self.messages_a = []
            self.messages_b = []
        else:
            raw_messages_a = self.store.load_messages(
                self.project_slug, session_id, "A"
            )
            raw_messages_b = self.store.load_messages(
                self.project_slug, session_id, "B"
            )
        self.loop_a.messages = []
        self._load_loop_history(self.loop_a, raw_messages_a)
        self.loop_b.messages = []
        self._load_loop_history(self.loop_b, raw_messages_b)
        self.messages_a = self._messages_to_frontend_view(self.loop_a.messages)
        self.messages_b = self._messages_to_frontend_view(self.loop_b.messages)
        self._reset_swap_state()

    def _reset_swap_state(self) -> None:
        self._turn_task = None
        self._b_turn_task = None
        self._a_last_text = ""
        self._b_pending_text = ""
        self._last_b_trigger_reason = ""
        self._a_error_history = []
        self._b_last_trigger_at = 0.0
        self._b_trigger_times = []

    async def _cancel_task(self, task: asyncio.Task | None) -> None:
        if not task or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
