import asyncio

import pytest

from desktop.server.session import DesktopSession
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
    assert sent == [{"type": "TextChunk", "data": {"text": "hi"}}]


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
