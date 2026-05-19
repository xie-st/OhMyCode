import asyncio

import pytest

from desktop.server.session import DesktopSession
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.messages import TextChunk, TurnComplete


async def _wait_until(predicate, timeout=1.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not met before timeout")


@pytest.mark.asyncio
async def test_user_input_triggers_window_b_turn(monkeypatch):
    instances = []

    class FakeLoop:
        def __init__(self, config, confirm_fn=None):
            self.config = config
            self.confirm_fn = confirm_fn
            self.bus = None
            self.messages = []
            self.role = "A" if not instances else "B"
            instances.append(self)

        def initialize(self):
            return None

        def set_event_bus(self, bus):
            self.bus = bus

        def add_user_message(self, text, image_blocks=None):
            self.messages.append(text)

        async def stream_turn(self):
            if self.role == "A":
                event = TurnComplete("stop", None)
            else:
                event = TextChunk("coaching note")
            await self.bus.publish(event)
            yield event

    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    sent = []
    session = DesktopSession(OhMyCodeConfig(), sent.append)

    await session.handle_user_input("inspect this")

    await asyncio.wait_for(session._turn_task, timeout=1)
    await _wait_until(lambda: any(item.get("window") == "B" for item in sent))

    assert any(item.get("type") == "TurnComplete" for item in sent)
    assert {
        "type": "TextChunk",
        "data": {"text": "coaching note"},
        "window": "B",
    } in sent
    assert len(instances[1].messages) == 1
    assert "[trigger_reason] user_input" in instances[1].messages[0]
    assert "[profile_snapshot] User profile snapshot" in instances[1].messages[0]
