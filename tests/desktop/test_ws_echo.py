from fastapi.testclient import TestClient

import desktop.server.ws as ws_module
from desktop.server.main import app


class FakeSession:
    inputs = []
    cancelled = 0

    def __init__(self, config, ws_send):
        self.config = config
        self.ws_send = ws_send

    async def handle_user_input(self, text):
        self.inputs.append(text)

    async def cancel(self):
        type(self).cancelled += 1


def test_ws_routes_user_input(monkeypatch):
    FakeSession.inputs = []
    FakeSession.cancelled = 0
    monkeypatch.setattr(ws_module, "DesktopSession", FakeSession)

    with TestClient(app).websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "user_input", "data": {"text": "hello"}})
        websocket.send_json({"type": "cancel"})

    assert FakeSession.inputs == ["hello"]
    assert FakeSession.cancelled >= 1


def test_ws_echoes_json_payload(monkeypatch):
    monkeypatch.setattr(ws_module, "DesktopSession", FakeSession)

    with TestClient(app).websocket_connect("/ws") as websocket:
        payload = {"type": "ping", "data": {"x": 1}}

        websocket.send_json(payload)

        assert websocket.receive_json() == {"type": "echo", "data": payload}


def test_ws_reports_invalid_json(monkeypatch):
    monkeypatch.setattr(ws_module, "DesktopSession", FakeSession)

    with TestClient(app).websocket_connect("/ws") as websocket:
        websocket.send_text("{")

        assert websocket.receive_json()["type"] == "error"
