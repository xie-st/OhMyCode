from fastapi.testclient import TestClient

import desktop.server.ws as ws_module
from desktop.server.main import app


class FakeSession:
    inputs = []
    cancelled = 0
    muted = []
    permissions = []
    saved = []

    def __init__(self, config, ws_send, session_id=None):
        self.config = config
        self.ws_send = ws_send
        self.session = type(
            "SessionMeta",
            (),
            {
                "id": session_id or "session-1",
                "title": "New conversation",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "project_slug": "project-one",
            },
        )()
        self.messages_a = []
        self.messages_b = []

    def current_session_payload(self):
        return {
            "id": self.session.id,
            "title": self.session.title,
            "created_at": self.session.created_at,
            "updated_at": self.session.updated_at,
            "project_slug": self.session.project_slug,
        }

    async def handle_user_input(self, text, target="A"):
        self.inputs.append((text, target))

    async def cancel(self):
        type(self).cancelled += 1

    def set_b_muted(self, muted):
        type(self).muted.append(muted)

    def resolve_permission(self, request_id, answer):
        type(self).permissions.append((request_id, answer))
        return True

    def save_messages(self, target, messages):
        type(self).saved.append((target, messages))
        if target == "B":
            self.messages_b = messages
        else:
            self.messages_a = messages


def test_ws_routes_user_input(monkeypatch):
    FakeSession.inputs = []
    FakeSession.cancelled = 0
    FakeSession.muted = []
    FakeSession.permissions = []
    FakeSession.saved = []
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


def test_ws_saves_session_messages(monkeypatch):
    FakeSession.saved = []
    monkeypatch.setattr(ws_module, "DesktopSession", FakeSession)

    with TestClient(app).websocket_connect("/ws?session=session-2") as websocket:
        _consume_existing_session_startup(websocket)
        websocket.send_json(
            {
                "type": "save_session",
                "data": {
                    "target": "A",
                    "messages": [{"role": "user", "text": "persist me"}],
                },
            }
        )

    assert FakeSession.saved == [("A", [{"role": "user", "text": "persist me"}])]


def _consume_runtime_info(websocket):
    """Drop the server's startup runtime_info push so subsequent assertions
    look at the test-specific response."""
    first = websocket.receive_json()
    assert first["type"] == "runtime_info"
    assert {"cwd", "a_model", "b_model", "provider"} <= set(first["data"].keys())


def _consume_existing_session_startup(websocket):
    _consume_runtime_info(websocket)
    assert websocket.receive_json()["type"] == "current_session"
    assert websocket.receive_json()["type"] == "history_loaded"


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
