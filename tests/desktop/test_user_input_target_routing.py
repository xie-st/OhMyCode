import asyncio

import pytest

from desktop.server.session import DesktopSession
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.messages import TextChunk


class RoutedLoop:
    instances = []

    def __init__(self, config, confirm_fn=None):
        self.config = config
        self.confirm_fn = confirm_fn
        self.bus = None
        self.messages = []
        self.stream_started = 0
        self.release = asyncio.Event()
        self.role = "A" if not RoutedLoop.instances else "B"
        RoutedLoop.instances.append(self)

    def initialize(self):
        return None

    def set_event_bus(self, bus):
        self.bus = bus

    def add_user_message(self, text, image_blocks=None):
        self.messages.append(text)

    async def stream_turn(self):
        self.stream_started += 1
        await self.bus.publish(TextChunk(f"{self.role} reply"))
        await self.release.wait()
        yield TextChunk("ignored")


@pytest.fixture(autouse=True)
def reset_fake_loop():
    RoutedLoop.instances = []


@pytest.mark.asyncio
async def test_target_a_routes_to_window_a(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", RoutedLoop)
    sent = []
    session = DesktopSession(OhMyCodeConfig(), sent.append)
    monkeypatch.setattr(session, "_schedule_b_trigger", lambda reason: None)

    await session.handle_user_input("main task", target="A")
    await asyncio.sleep(0)
    session.loop_a.release.set()
    await session._turn_task

    assert session.loop_a.messages == ["main task"]
    assert session.loop_a.stream_started == 1
    assert session.loop_b.messages == []
    assert sent[0]["type"] == "current_session"
    assert sent[1:] == [{"type": "TextChunk", "data": {"text": "A reply"}}]


@pytest.mark.asyncio
async def test_target_b_routes_directly_to_window_b(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", RoutedLoop)
    sent = []
    session = DesktopSession(OhMyCodeConfig(), sent.append)

    task = asyncio.create_task(session.handle_user_input("explain this", target="B"))
    await asyncio.sleep(0)
    session.loop_b.release.set()
    await task

    assert session.loop_a.messages == []
    assert session.loop_b.messages == ["explain this"]
    assert session.loop_b.stream_started == 1
    assert sent[0]["type"] == "current_session"
    assert sent[1:] == [
        {"type": "TextChunk", "data": {"text": "B reply"}, "window": "B"}
    ]
