import asyncio

import pytest
from fastapi.testclient import TestClient

import desktop.server.ws as ws_module
from desktop.server.main import app
from desktop.server.session import DesktopSession
from ohmycode.config.config import OhMyCodeConfig


@pytest.mark.asyncio
async def test_session_cancel_stops_all_tasks(monkeypatch):
    monkeypatch.setattr("desktop.server.session.ConversationLoop", FakeLoop)
    session = DesktopSession(OhMyCodeConfig(), lambda _: None)
    session._turn_task = asyncio.create_task(asyncio.sleep(60))
    session._b_turn_task = asyncio.create_task(asyncio.sleep(60))
    background_task = asyncio.create_task(asyncio.sleep(60))
    session._background_tasks.add(background_task)

    await session.cancel()

    assert session._turn_task.cancelled()
    assert session._b_turn_task.cancelled()
    assert background_task.cancelled()


def test_ws_disconnect_calls_cancel(monkeypatch):
    FakeSession.cancelled = 0
    monkeypatch.setattr(ws_module, "DesktopSession", FakeSession)

    with TestClient(app).websocket_connect("/ws"):
        pass

    assert FakeSession.cancelled == 1


class FakeLoop:
    def __init__(self, config, confirm_fn=None):
        self.config = config
        self.confirm_fn = confirm_fn

    def initialize(self):
        return None

    def set_event_bus(self, bus):
        return None


class FakeSession:
    cancelled = 0

    def __init__(self, config, ws_send):
        self.config = config
        self.ws_send = ws_send

    async def cancel(self):
        type(self).cancelled += 1
