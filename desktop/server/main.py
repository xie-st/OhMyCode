import asyncio
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from desktop.server.profile_api import router as profile_router
from desktop.server.sessions_api import router as sessions_router
from desktop.server.ws import router as ws_router


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="OhMyCode Desktop")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(profile_router)
app.include_router(sessions_router)
app.include_router(ws_router)


@app.on_event("startup")
async def startup_banner() -> None:
    print("OhMyCode Desktop server starting on ws://localhost:8765/ws")
    loop = asyncio.get_running_loop()
    policy = asyncio.get_event_loop_policy()
    print(
        f"[asyncio] policy={type(policy).__name__} loop={type(loop).__name__}"
    )
