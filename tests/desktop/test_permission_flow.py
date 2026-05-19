import asyncio

import pytest

from desktop.server.session import DesktopSession
from ohmycode.config.config import OhMyCodeConfig


class FakeLoop:
    def __init__(self, config, confirm_fn=None):
        self.config = config
        self.confirm_fn = confirm_fn
        self.bus = None
        # R1.6 kernel-form persistence reads loop.messages to build the
        # initial frontend view; keep an empty list so the test doesn't
        # depend on any history.
        self.messages: list = []

    def initialize(self):
        return None

    def set_event_bus(self, bus):
        self.bus = bus


async def _wait_for_request(sent_payloads):
    deadline = asyncio.get_running_loop().time() + 1.0
    while asyncio.get_running_loop().time() < deadline:
        if sent_payloads:
            return sent_payloads[-1]
        await asyncio.sleep(0)
    raise AssertionError("permission request was not sent")


@pytest.mark.asyncio
async def test_permission_allow_once(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    sent_payloads = []
    session = DesktopSession(OhMyCodeConfig(), sent_payloads.append)
    confirm = session._make_confirm_fn("A")

    task = asyncio.create_task(confirm("read", {"path": "/tmp/x"}))
    payload = await _wait_for_request(sent_payloads)
    request_id = payload["data"]["request_id"]

    assert session.resolve_permission(request_id, "y") is True
    assert await task == "y"
    assert "read" not in session._auto_approved_tools


@pytest.mark.asyncio
async def test_permission_always_allow_adds_to_auto_approved(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    sent_payloads = []
    session = DesktopSession(OhMyCodeConfig(), sent_payloads.append)
    confirm = session._make_confirm_fn("A")

    task = asyncio.create_task(confirm("bash", {"cmd": "pwd"}))
    payload = await _wait_for_request(sent_payloads)
    request_id = payload["data"]["request_id"]

    assert session.resolve_permission(request_id, "a") is True
    assert await task == "a"
    assert "bash" in session._auto_approved_tools

    assert await confirm("bash", {"cmd": "date"}) == "y"
    assert len(sent_payloads) == 1


@pytest.mark.asyncio
async def test_permission_deny_returns_n(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    sent_payloads = []
    session = DesktopSession(OhMyCodeConfig(), sent_payloads.append)
    confirm = session._make_confirm_fn("A")

    task = asyncio.create_task(confirm("write", {"path": "/tmp/x"}))
    payload = await _wait_for_request(sent_payloads)
    request_id = payload["data"]["request_id"]

    assert session.resolve_permission(request_id, "n") is True
    assert await task == "n"


@pytest.mark.asyncio
async def test_permission_timeout_returns_n(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    monkeypatch.setattr("desktop.server.session.PERMISSION_TIMEOUT_SECONDS", 0.01)
    sent_payloads = []
    session = DesktopSession(OhMyCodeConfig(), sent_payloads.append)
    confirm = session._make_confirm_fn("A")

    assert await confirm("edit", {"path": "/tmp/x"}) == "n"
    assert sent_payloads[-1]["type"] == "permission_request"
    assert session._pending_perms == {}


@pytest.mark.asyncio
async def test_permission_response_unknown_request_returns_false(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    session = DesktopSession(OhMyCodeConfig(), lambda _: None)

    assert session.resolve_permission("missing", "y") is False
