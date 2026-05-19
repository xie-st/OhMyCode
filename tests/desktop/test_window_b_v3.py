import asyncio

import pytest

from desktop.server.profile import UserProfile
from desktop.server.session import DesktopSession
from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.messages import TextChunk, ToolCallResult, ToolCallStart, TurnComplete


class PassiveLoop:
    instances = []

    def __init__(self, config, confirm_fn=None):
        self.config = config
        self.confirm_fn = confirm_fn
        self.bus = None
        self.messages = []
        self.stream_started = 0
        self.role = "A" if not PassiveLoop.instances else "B"
        PassiveLoop.instances.append(self)

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


@pytest.fixture(autouse=True)
def reset_loop():
    PassiveLoop.instances = []


async def _settle():
    for _ in range(5):
        await asyncio.sleep(0)


def _make_session(monkeypatch, sent=None):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", PassiveLoop)
    if sent is None:
        sent = []
    return DesktopSession(OhMyCodeConfig(), sent.append)


@pytest.mark.asyncio
async def test_user_input_triggers_b_immediately(monkeypatch):
    session = _make_session(monkeypatch)
    called = []

    def schedule(reason):
        called.append(reason)

    monkeypatch.setattr(session, "_schedule_b_trigger", schedule)

    await session.handle_user_input("work on A", target="A")

    assert called == ["user_input"]
    assert session.loop_a.messages == ["work on A"]


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["[Silent]", "[SILENT]", " [silent] "])
async def test_b_silent_sentinel_case_insensitive(monkeypatch, token):
    sent = []
    session = _make_session(monkeypatch, sent)

    await session._on_event_b(TextChunk(token))
    await session._on_event_b(TurnComplete("stop", None))

    assert sent == [
        {
            "type": "b_silent",
            "window": "B",
            "data": {"reason": "turn_complete"},
        }
    ]


@pytest.mark.asyncio
async def test_b_silent_buffers_until_sentinel_known(monkeypatch):
    sent = []
    session = _make_session(monkeypatch, sent)

    await session._on_event_b(TextChunk("[sil"))
    assert sent == []

    await session._on_event_b(TextChunk("ent]"))
    await session._on_event_b(TurnComplete("stop", None))

    assert sent[0]["type"] == "b_silent"


@pytest.mark.asyncio
async def test_tool_start_and_repeated_error_do_not_trigger_b(monkeypatch):
    session = _make_session(monkeypatch)
    called = []
    monkeypatch.setattr(session, "_schedule_b_trigger", called.append)

    await session._on_event_a(ToolCallStart("read", "tool-1", {"path": "x.py"}))
    await session._on_event_a(ToolCallResult("tool-1", "same failure", True))
    await session._on_event_a(ToolCallResult("tool-2", "same failure", True))
    await _settle()

    assert called == []


@pytest.mark.asyncio
async def test_maybe_trigger_b_observation_contains_reason_profile_and_context(monkeypatch):
    session = _make_session(monkeypatch)
    session._a_last_text = "A recent context"

    await session._maybe_trigger_b("turn_complete")

    assert session._last_b_trigger_reason == "turn_complete"
    assert "[trigger_reason] turn_complete" in session.loop_b.messages[0]
    assert "[profile_snapshot] User profile snapshot" in session.loop_b.messages[0]
    assert "[window_a_context] A recent context" in session.loop_b.messages[0]


def test_inspirations_section_omitted_when_empty(monkeypatch):
    monkeypatch.setattr(UserProfile, "load_inspirations", lambda self: "")
    session = _make_session(monkeypatch)

    assert "## Inspiration resources" not in session.loop_b.config.system_prompt_append


def test_inspirations_section_included(monkeypatch):
    monkeypatch.setattr(UserProfile, "load_inspirations", lambda self: "# A useful note")
    session = _make_session(monkeypatch)

    assert "## Inspiration resources\n# A useful note" in session.loop_b.config.system_prompt_append


def test_concept_dispositions_in_snapshot():
    profile = UserProfile(cwd="/tmp/fake")
    profile.concept_dispositions = {"py.async": "learn"}

    snapshot = profile.snapshot_for_b()

    assert "dispositions: py.async=learn" in snapshot
