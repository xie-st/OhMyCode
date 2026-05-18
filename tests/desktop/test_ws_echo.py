from fastapi.testclient import TestClient

from desktop.server.main import app


def test_ws_echoes_json_payload():
    with TestClient(app).websocket_connect("/ws") as websocket:
        payload = {"type": "ping", "data": {"x": 1}}

        websocket.send_json(payload)

        assert websocket.receive_json() == {"type": "echo", "data": payload}


def test_ws_reports_invalid_json():
    with TestClient(app).websocket_connect("/ws") as websocket:
        websocket.send_text("{")

        assert websocket.receive_json()["type"] == "error"
