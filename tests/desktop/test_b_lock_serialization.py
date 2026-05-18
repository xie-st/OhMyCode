import asyncio

import pytest

from desktop.server.session import DesktopSession
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.messages import TextChunk, ToolCallStart


@pytest.mark.asyncio
async def test_b_lock_allows_only_one_active_b_turn(monkeypatch):
    monkeypatch.setattr("desktop.server.session.B_TOOL_TRIGGER_DELAY_SECONDS", 0.0)
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
            if self.role == "A":
                for index in range(3):
                    event = ToolCallStart("read", f"tool-{index}", {"path": "x.py"})
                    await self.bus.publish(event)
                    yield event
                return

            await asyncio.sleep(0.1)
            event = TextChunk("one b turn")
            await self.bus.publish(event)
            yield event

    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    session = DesktopSession(OhMyCodeConfig(), lambda _: None)

    await session.handle_user_input("trigger tools")
    await asyncio.wait_for(session._turn_task, timeout=1)
    for _ in range(5):
        if session._b_turn_task is not None:
            break
        await asyncio.sleep(0)
    await asyncio.wait_for(session._b_turn_task, timeout=1)

    assert instances[1].stream_started == 1
    assert len(instances[1].messages) == 1
    assert "[Observation] Window A is running tool_executing" in instances[1].messages[0]
    assert "[Profile] User profile snapshot" in instances[1].messages[0]
