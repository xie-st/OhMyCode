import asyncio

import pytest

from desktop.server.session import DesktopSession
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.messages import TextChunk


@pytest.mark.asyncio
async def test_b_lock_allows_only_one_active_b_turn(monkeypatch):
    monkeypatch.setattr("desktop.server.session.B_COOLDOWN_SECONDS", 0.0)
    instances = []

    class FakeLoop:
        def __init__(self, config, confirm_fn=None):
            self.config = config
            self.confirm_fn = confirm_fn
            self.bus = None
            self.messages = []
            self.stream_started = 0
            self.role = "A" if not instances else "B"
            instances.append(self)

        def initialize(self):
            return None

        def set_event_bus(self, bus):
            self.bus = bus

        def add_user_message(self, text, image_blocks=None):
            self.messages.append(text)

        async def stream_turn(self):
            self.stream_started += 1
            await asyncio.sleep(0.1)
            event = TextChunk("one b turn")
            await self.bus.publish(event)
            yield event

    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    session = DesktopSession(OhMyCodeConfig(), lambda _: None)

    first = asyncio.create_task(session._maybe_trigger_b("user_input"))
    await asyncio.sleep(0)
    second = asyncio.create_task(session._maybe_trigger_b("turn_complete"))
    await asyncio.wait_for(asyncio.gather(first, second), timeout=1)

    assert instances[1].stream_started == 1
    assert len(instances[1].messages) == 1
    assert "[trigger_reason] user_input" in instances[1].messages[0]
    assert "[profile_snapshot] User profile snapshot" in instances[1].messages[0]
