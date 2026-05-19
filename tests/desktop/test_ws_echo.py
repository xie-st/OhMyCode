from fastapi.testclient import TestClient

import desktop.server.ws as ws_module
from desktop.server.main import app


class FakeSession:
    inputs = []
    cancelled = 0
    muted = []
    permissions = []

    def __init__(self, config, ws_send):
        self.config = config
        self.ws_send = ws_send

    async def handle_user_input(self, text, target="A"):
        self.inputs.append((text, target))

    async def cancel(self):
        type(self).cancelled += 1

    def set_b_muted(self, muted):
        type(self).muted.append(muted)

    def resolve_permission(self, request_id, answer):
        type(self).permissions.append((request_id, answer))
        return True


def test_ws_routes_user_input(monkeypatch):
    FakeSession.inputs = []
    FakeSession.cancelled = 0
    FakeSession.muted = []
    FakeSession.permissions = []
    monkeypatch.setattr(ws_module, "DesktopSession", FakeSession)

    with TestClient(app).websocket_connect("/ws") as websocket:
        _consume_runtime_info(websocket)
        websocket.send_json(
            {"type": "user_input", "data": {"text": "hello", "target": "B"}}
        )
        websocket.send_json({"type": "user_typing", "data": {"typing": True}})
        websocket.send_json(
            {
                "type": "permission_response",
                "data": {"request_id": "req-1", "answer": "a"},
            }
        )
        websocket.send_json({"type": "cancel"})

    assert FakeSession.inputs == [("hello", "B")]
    assert FakeSession.muted == [True]
    assert FakeSession.permissions == [("req-1", "a")]
    assert FakeSession.cancelled >= 1


def _consume_runtime_info(websocket):
    """Drop the server's startup runtime_info push so subsequent assertions
    look at the test-specific response."""
    first = websocket.receive_json()
    assert first["type"] == "runtime_info"
    assert {"cwd", "a_model", "b_model", "provider"} <= set(first["data"].keys())


def test_ws_echoes_json_payload(monkeypatch):
    monkeypatch.setattr(ws_module, "DesktopSession", FakeSession)

    with TestClient(app).websocket_connect("/ws") as websocket:
        _consume_runtime_info(websocket)
        payload = {"type": "ping", "data": {"x": 1}}

        websocket.send_json(payload)

        assert websocket.receive_json() == {"type": "echo", "data": payload}


def test_ws_reports_invalid_json(monkeypatch):
    monkeypatch.setattr(ws_module, "DesktopSession", FakeSession)

    with TestClient(app).websocket_connect("/ws") as websocket:
        _consume_runtime_info(websocket)
        websocket.send_text("{")

        assert websocket.receive_json()["type"] == "error"
