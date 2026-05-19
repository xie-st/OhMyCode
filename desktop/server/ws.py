import asyncio
import os
from json import JSONDecodeError
from pathlib import Path

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from desktop.server.session import DesktopSession
from ohmycode.config.config import load_config


router = APIRouter()
_connection_lock = asyncio.Lock()
_connected = False


def _short_cwd() -> str:
    """Render cwd as a short relative path for the status bar."""
    cwd = Path(os.getcwd())
    try:
        rel = cwd.relative_to(Path.home())
        return f"~/{rel.as_posix()}"
    except ValueError:
        return cwd.as_posix()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    global _connected
    async with _connection_lock:
        if _connected:
            await websocket.send_json({"type": "error", "reason": "already_connected"})
            await websocket.close()
            return
        _connected = True

    send_lock = asyncio.Lock()

    async def ws_send(payload: dict) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    session: DesktopSession | None = None
    try:
        config = load_config({})
        session = DesktopSession(config, ws_send)
        websocket.app.state.session = session
        await ws_send(
            {
                "type": "runtime_info",
                "data": {
                    "cwd": _short_cwd(),
                    "a_model": config.model,
                    "b_model": config.window_b_model or config.model,
                    "provider": config.provider,
                },
            }
        )
        while True:
            try:
                payload = await websocket.receive_json()
            except JSONDecodeError as exc:
                await ws_send({"type": "error", "data": {"message": str(exc)}})
                continue

            message_type = payload.get("type")
            if message_type == "user_input":
                data = payload.get("data", {})
                text = data.get("text", "")
                target = "B" if data.get("target") == "B" else "A"
                await session.handle_user_input(text, target)
            elif message_type == "user_typing":
                is_typing = bool(payload.get("data", {}).get("typing", False))
                session.set_b_muted(is_typing)
            elif message_type == "permission_response":
                data = payload.get("data", {})
                request_id = str(data.get("request_id", ""))
                answer = str(data.get("answer", "n"))
                session.resolve_permission(request_id, answer)
            elif message_type == "cancel":
                await session.cancel()
            else:
                await ws_send({"type": "echo", "data": payload})
    except WebSocketDisconnect:
        return
    finally:
        if session is not None:
            await session.cancel()
            if getattr(websocket.app.state, "session", None) is session:
                websocket.app.state.session = None
        async with _connection_lock:
            _connected = False
