import pytest

from desktop.server.sessions import SessionStore


@pytest.fixture(autouse=True)
def isolate_desktop_profile_path(tmp_path, monkeypatch):
    target = tmp_path / "profile.json"
    monkeypatch.setattr("desktop.server.profile._profile_path", lambda cwd: target)
    store = SessionStore(root=tmp_path / "projects")
    monkeypatch.setattr("desktop.server.session.sessions_store", store)
    monkeypatch.setattr("desktop.server.sessions.sessions_store", store)
    monkeypatch.setattr("desktop.server.sessions_api.sessions_store", store)
    monkeypatch.setattr(
        "desktop.server.ws.sessions_store",
        SessionStore(root=tmp_path / "projects"),
        raising=False,
    )
