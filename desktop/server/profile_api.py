from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/api/profile")


def _get_profile(request: Request):
    session = getattr(request.app.state, "session", None)
    if session is None or getattr(session, "profile", None) is None:
        raise HTTPException(status_code=503, detail="No active desktop session")
    return session.profile


@router.get("")
async def get_profile(request: Request):
    """Return full profile as JSON for the active desktop session."""
    return _get_profile(request)._to_json_data()


@router.delete("/evidence/{evidence_id}")
async def delete_evidence(evidence_id: str, request: Request):
    """Delete a single evidence entry across all concepts and gaps."""
    profile = _get_profile(request)
    profile.delete_evidence(evidence_id)
    return {"status": "deleted"}


@router.delete("")
async def clear_profile(request: Request):
    """Wipe the active session profile."""
    profile = _get_profile(request)
    profile.clear()
    return {"status": "cleared"}
