from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from desktop.server.profile_api import router as profile_router
from desktop.server.ws import router as ws_router


app = FastAPI(title="OhMyCode Desktop")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(profile_router)
app.include_router(ws_router)
