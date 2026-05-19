import asyncio

import pytest

from desktop.server.session import DesktopSession
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.messages import TextChunk, ToolCallStart


async def _wait_until(predicate, timeout=1.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not met before timeout")


@pytest.mark.asyncio
async def test_tool_call_from_a_triggers_window_b_turn(monkeypatch):
    monkeypatch.setattr("desktop.server.session.B_TOOL_TRIGGER_DELAY_SECONDS", 0.01)
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
                event = ToolCallStart("read", "tool-1", {"path": "x.py"})
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

    # Lazy session-create pushes a `current_session` event before the first
    # turn now (R1.B), so skip past startup events to find ToolCallStart.
    tool_call_starts = [item for item in sent if item.get("type") == "ToolCallStart"]
    assert tool_call_starts[0] == {
        "type": "ToolCallStart",
        "data": {
            "tool_name": "read",
            "tool_use_id": "tool-1",
            "params": {"path": "x.py"},
            "params_preview": '{"path": "x.py"}',
        },
    }
    assert {
        "type": "TextChunk",
        "data": {"text": "coaching note"},
        "window": "B",
    } in sent
    assert len(instances[1].messages) == 1
    assert "[Observation] Window A is running tool_executing" in instances[1].messages[0]
    assert "[Profile] User profile snapshot" in instances[1].messages[0]
