from dataclasses import asdict

from fastapi import APIRouter

from desktop.server.sessions import project_slug_for_cwd, sessions_store


router = APIRouter()


@router.get("/api/sessions")
async def list_sessions() -> list[dict[str, str]]:
    slug = project_slug_for_cwd()
    return [asdict(session) for session in sessions_store.list_sessions(slug)]


@router.post("/api/sessions")
async def create_session() -> dict[str, str]:
    slug = project_slug_for_cwd()
    return asdict(sessions_store.create_new(slug))


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, bool]:
    slug = project_slug_for_cwd()
    sessions_store.delete(slug, session_id)
    return {"ok": True}
