import asyncio

import pytest

from desktop.server.session import DesktopSession
from desktop.server.session import _derive_title
from desktop.server.sessions import SessionStore
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.messages import (
    TextChunk,
    TokenUsage,
    ToolCallResult,
    ToolCallStart,
    TurnComplete,
)


class FakeLoop:
    def __init__(self, config, confirm_fn=None):
        self.config = config
        self.confirm_fn = confirm_fn
        self.bus = None
        self.messages = []
        self.stream_started = 0
        self.release = asyncio.Event()

    def initialize(self):
        return None

    def set_event_bus(self, bus):
        self.bus = bus

    def add_user_message(self, text, image_blocks=None):
        self.messages.append(text)

    async def stream_turn(self):
        self.stream_started += 1
        await self.bus.publish(TextChunk("hi"))
        await self.release.wait()
        yield TextChunk("ignored")


@pytest.mark.asyncio
async def test_on_event_serializes_text_chunk(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    sent = []
    session = DesktopSession(OhMyCodeConfig(), sent.append)

    await session._on_event_a(TextChunk("hello"))

    assert sent == [{"type": "TextChunk", "data": {"text": "hello"}}]


@pytest.mark.asyncio
async def test_on_event_serializes_tool_events_and_usage(monkeypatch):
    monkeypatch.setattr("desktop.server.session.B_TOOL_TRIGGER_DELAY_SECONDS", 0.0)
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    sent = []
    session = DesktopSession(OhMyCodeConfig(), sent.append)

    await session._on_event_a(ToolCallStart("read", "tool-1", {"path": "x.py"}))
    await session._on_event_a(ToolCallResult("tool-1", "ok", False))
    await session._on_event_a(
        TurnComplete("stop", TokenUsage(1, 2, 3))
    )

    assert sent == [
        {
            "type": "ToolCallStart",
            "data": {
                "tool_name": "read",
                "tool_use_id": "tool-1",
                "params": {"path": "x.py"},
                "params_preview": '{"path": "x.py"}',
            },
        },
        {
            "type": "ToolCallResult",
            "data": {
                "tool_use_id": "tool-1",
                "result": "ok",
                "is_error": False,
                "result_preview": "ok",
                "is_truncated": False,
            },
        },
        {
            "type": "TurnComplete",
            "data": {
                "finish_reason": "stop",
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 2,
                    "total_tokens": 3,
                },
            },
        },
    ]
    session.loop_b.release.set()
    if session._b_turn_task is not None:
        await session._b_turn_task


@pytest.mark.asyncio
async def test_user_input_starts_one_turn(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    sent = []
    session = DesktopSession(OhMyCodeConfig(), sent.append)

    await session.handle_user_input("first")
    await asyncio.sleep(0)
    await session.handle_user_input("second")
    await asyncio.sleep(0)
    session.loop_a.release.set()
    await session._turn_task

    assert session.loop_a.messages == ["first"]
    assert session.loop_a.stream_started == 1
    assert sent[0]["type"] == "current_session"
    assert sent[0]["data"]["title"] == "first"
    assert sent[1:] == [{"type": "TextChunk", "data": {"text": "hi"}}]


@pytest.mark.asyncio
async def test_new_desktop_session_is_uncommitted_until_user_input(tmp_path, monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    monkeypatch.setattr(
        "desktop.server.session.DesktopSession._project_slug",
        lambda self: "slug-one",
    )
    store = SessionStore(root=tmp_path / "projects")
    sent = []

    session = DesktopSession(OhMyCodeConfig(), sent.append, store=store)

    assert session.session is None
    assert session.messages_a == []
    assert session.messages_b == []
    assert store.list_sessions("slug-one") == []

    await session.handle_user_input("A demo title")
    await asyncio.sleep(0)
    session.loop_a.release.set()
    await session._turn_task

    [created] = store.list_sessions("slug-one")
    assert created.title == "A demo title"
    assert sent[0]["type"] == "current_session"
    assert sent[0]["data"]["id"] == created.id


@pytest.mark.asyncio
async def test_existing_untitled_session_title_updates_from_first_user_input(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    monkeypatch.setattr(
        "desktop.server.session.DesktopSession._project_slug",
        lambda self: "slug-one",
    )
    store = SessionStore(root=tmp_path / "projects")
    session_meta = store.create_new("slug-one")
    sent = []
    session = DesktopSession(
        OhMyCodeConfig(),
        sent.append,
        session_id=session_meta.id,
        store=store,
    )

    task = asyncio.create_task(
        session.handle_user_input("B demo routes nicely", target="B")
    )
    await asyncio.sleep(0)
    session.loop_b.release.set()
    await task

    [saved] = store.list_sessions("slug-one")
    assert saved.title == "B demo routes nicely"
    assert sent[0]["type"] == "current_session"
    assert sent[0]["data"]["title"] == "B demo routes nicely"


def test_derive_title_collapses_whitespace_and_truncates():
    assert _derive_title("  hello   world  ") == "hello world"
    assert _derive_title("") == "\u65b0\u4f1a\u8bdd"
    assert _derive_title("x" * 31) == ("x" * 30) + "\u2026"


@pytest.mark.asyncio
async def test_cancel_stops_active_turn(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    session = DesktopSession(OhMyCodeConfig(), lambda _: asyncio.sleep(0))

    await session.handle_user_input("hello")
    await asyncio.sleep(0)
    await session.cancel()

    assert session._turn_task.cancelled()


def test_window_a_gets_windows_shell_hint_on_windows(monkeypatch):
    monkeypatch.setattr("desktop.server.session.os.name", "nt")
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)

    session = DesktopSession(OhMyCodeConfig(system_prompt_append="base"), lambda _: None)

    assert "base" in session.loop_a.config.system_prompt_append
    assert "running on Windows" in session.loop_a.config.system_prompt_append
    assert "cmd.exe" in session.loop_a.config.system_prompt_append
    assert session.loop_b.config.system_prompt_append.count("running on Windows") == 0


def test_existing_session_history_loads_into_both_loops(tmp_path, monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    store = SessionStore(root=tmp_path / "projects")
    session_meta = store.create_new("slug-one")
    store.save_messages(
        "slug-one",
        session_meta.id,
        "A",
        [{"role": "user", "text": "old A user"}, {"role": "assistant", "text": "old A"}],
    )
    store.save_messages(
        "slug-one",
        session_meta.id,
        "B",
        [{"role": "assistant", "text": "old B"}],
    )
    monkeypatch.setattr(
        "desktop.server.session.DesktopSession._project_slug",
        lambda self: "slug-one",
    )

    session = DesktopSession(
        OhMyCodeConfig(),
        lambda _: None,
        session_id=session_meta.id,
        store=store,
    )

    assert [message.content for message in session.loop_a.messages] == [
        "old A user",
        "old A",
    ]
    assert [message.content for message in session.loop_b.messages] == ["old B"]


@pytest.mark.asyncio
async def test_swap_to_replaces_history_without_recreating_loops(tmp_path, monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    monkeypatch.setattr(
        "desktop.server.session.DesktopSession._project_slug",
        lambda self: "slug-one",
    )
    store = SessionStore(root=tmp_path / "projects")
    first = store.create_new("slug-one", title="First")
    second = store.create_new("slug-one", title="Second")
    store.save_messages(
        "slug-one",
        second.id,
        "A",
        [
            {"role": "user", "text": "new A user"},
            {"role": "assistant", "text": "new A assistant"},
        ],
    )
    store.save_messages(
        "slug-one",
        second.id,
        "B",
        [{"role": "assistant", "text": "new B assistant"}],
    )
    session = DesktopSession(
        OhMyCodeConfig(),
        lambda _: None,
        session_id=first.id,
        store=store,
    )
    loop_a = session.loop_a
    loop_b = session.loop_b
    session._a_last_text = "old text"
    session._a_error_history = ["old error"]
    session._pending_tool_triggers = {"tool-1"}
    session._b_last_trigger_at = 123.0
    session._b_trigger_times = [100.0]

    await session.swap_to(second.id)

    assert session.loop_a is loop_a
    assert session.loop_b is loop_b
    assert session.session is not None
    assert session.session.id == second.id
    assert [message.content for message in session.loop_a.messages] == [
        "new A user",
        "new A assistant",
    ]
    assert [message.content for message in session.loop_b.messages] == [
        "new B assistant"
    ]
    assert session.messages_a == store.load_messages("slug-one", second.id, "A")
    assert session.messages_b == store.load_messages("slug-one", second.id, "B")
    assert session._a_last_text == ""
    assert session._a_error_history == []
    assert session._pending_tool_triggers == set()
    assert session._b_last_trigger_at == 0.0
    assert session._b_trigger_times == []


def test_save_messages_ignores_uncommitted_session(tmp_path, monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    monkeypatch.setattr(
        "desktop.server.session.DesktopSession._project_slug",
        lambda self: "slug-one",
    )
    store = SessionStore(root=tmp_path / "projects")
    session = DesktopSession(OhMyCodeConfig(), lambda _: None, store=store)

    session.save_messages("B", [{"role": "assistant", "text": "not yet"}])

    assert store.list_sessions("slug-one") == []


@pytest.mark.asyncio
async def test_window_b_confirm_fn_requests_permission(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    sent = []
    session = DesktopSession(OhMyCodeConfig(), sent.append)

    task = asyncio.create_task(
        session.loop_b.confirm_fn("read", {"path": "profile.json"})
    )
    await asyncio.sleep(0)
    request = sent[-1]
    request_id = request["data"]["request_id"]

    assert request["type"] == "permission_request"
    assert request["data"]["window"] == "B"
    assert request["data"]["tool_name"] == "read"
    assert session.resolve_permission(request_id, "y") is True
    assert await task == "y"
