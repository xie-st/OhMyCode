import asyncio

import pytest

from desktop.server.session import DesktopSession
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.messages import ToolCallResult, ToolCallStart, TurnComplete


class PassiveLoop:
    def __init__(self, config, confirm_fn=None):
        self.config = config
        self.confirm_fn = confirm_fn
        self.bus = None
        self.messages = []
        self.stream_started = 0

    def initialize(self):
        return None

    def set_event_bus(self, bus):
        self.bus = bus

    def add_user_message(self, text, image_blocks=None):
        self.messages.append(text)

    async def stream_turn(self):
        self.stream_started += 1
        if False:
            yield None


def _make_session(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", PassiveLoop)
    return DesktopSession(OhMyCodeConfig(), lambda _: None)


async def _settle():
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_trigger_delay_skips_fast_tools(monkeypatch):
    monkeypatch.setattr("desktop.server.session.B_TOOL_TRIGGER_DELAY_SECONDS", 0.01)
    session = _make_session(monkeypatch)

    await session._on_event_a(ToolCallStart("read", "tool-1", {"path": "x.py"}))
    await session._on_event_a(ToolCallResult("tool-1", "ok", False))
    await asyncio.sleep(0.02)

    assert session.loop_b.stream_started == 0


@pytest.mark.asyncio
async def test_b_cooldown_60s(monkeypatch):
    now = 100.0
    monkeypatch.setattr("desktop.server.session.B_COOLDOWN_SECONDS", 60.0)
    session = _make_session(monkeypatch)
    monkeypatch.setattr(asyncio.get_event_loop(), "time", lambda: now)

    await session._maybe_trigger_b("first")
    await session._maybe_trigger_b("second")

    assert session.loop_b.stream_started == 1


@pytest.mark.asyncio
async def test_user_typing_mutes_b(monkeypatch):
    session = _make_session(monkeypatch)

    session.set_b_muted(True)
    await session._maybe_trigger_b("tool_executing")
    session.set_b_muted(False)
    await session._maybe_trigger_b("tool_executing")

    assert session.loop_b.stream_started == 1


@pytest.mark.asyncio
async def test_continuous_edit_no_trigger(monkeypatch):
    now = 200.0
    session = _make_session(monkeypatch)
    monkeypatch.setattr(asyncio.get_event_loop(), "time", lambda: now)

    for index in range(5):
        await session.handle_user_input(f"edit file again {index}")
        session.loop_a.stream_started = 0
        now += 30.0

    await _settle()

    assert session.loop_b.stream_started == 0


@pytest.mark.asyncio
async def test_turn_complete_triggers_once_with_cooldown(monkeypatch):
    now = 300.0
    session = _make_session(monkeypatch)
    monkeypatch.setattr(asyncio.get_event_loop(), "time", lambda: now)

    await session._on_event_a(TurnComplete("stop", None))
    await _settle()
    now += 30.0
    await session._on_event_a(TurnComplete("stop", None))
    await _settle()

    assert session.loop_b.stream_started == 1


@pytest.mark.asyncio
async def test_repeated_error_triggers(monkeypatch):
    session = _make_session(monkeypatch)

    await session._on_event_a(ToolCallResult("tool-1", "same failure", True))
    await session._on_event_a(ToolCallResult("tool-2", "same failure", True))
    await _settle()

    assert session.loop_b.stream_started == 1


@pytest.mark.asyncio
async def test_rate_limit_5_per_10min(monkeypatch):
    now = 400.0
    session = _make_session(monkeypatch)
    monkeypatch.setattr("desktop.server.session.B_COOLDOWN_SECONDS", 0.0)
    monkeypatch.setattr(asyncio.get_event_loop(), "time", lambda: now)

    for index in range(6):
        await session._maybe_trigger_b(f"trigger-{index}")
        now += 1.0

    assert session.loop_b.stream_started == 5
