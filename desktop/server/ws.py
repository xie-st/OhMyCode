from json import JSONDecodeError

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect


router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            try:
                payload = await websocket.receive_json()
            except JSONDecodeError as exc:
                await websocket.send_json({"type": "error", "data": {"message": str(exc)}})
                continue

            await websocket.send_json({"type": "echo", "data": payload})
    except WebSocketDisconnect:
        return
