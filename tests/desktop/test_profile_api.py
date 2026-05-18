from fastapi.testclient import TestClient

from desktop.server.main import app
from desktop.server.profile import UserProfile


class FakeSession:
    def __init__(self, profile):
        self.profile = profile


def test_get_profile_returns_current_state(tmp_path, monkeypatch):
    target = tmp_path / "profile.json"
    monkeypatch.setattr("desktop.server.profile._profile_path", lambda cwd: target)
    profile = UserProfile.for_cwd("/tmp/fake")
    profile.observe_user_message("python pytest")
    app.state.session = FakeSession(profile)

    response = TestClient(app).get("/api/profile")

    assert response.status_code == 200
    data = response.json()
    assert data["skills"]["python"]["evidence_count"] >= 1
    assert data["cwd"] == "/tmp/fake"


def test_delete_evidence_removes_it(tmp_path, monkeypatch):
    target = tmp_path / "profile.json"
    monkeypatch.setattr("desktop.server.profile._profile_path", lambda cwd: target)
    profile = UserProfile.for_cwd("/tmp/fake")
    profile.observe_user_message("async await")
    evidence_id = profile.concepts["py.async"]["evidence"][0]["id"]
    app.state.session = FakeSession(profile)

    response = TestClient(app).delete(f"/api/profile/evidence/{evidence_id}")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    assert profile.concepts["py.async"]["evidence_count"] == 0
    assert profile.concepts["py.async"]["evidence"] == []


def test_clear_profile_resets_all_fields(tmp_path, monkeypatch):
    target = tmp_path / "profile.json"
    monkeypatch.setattr("desktop.server.profile._profile_path", lambda cwd: target)
    profile = UserProfile.for_cwd("/tmp/fake")
    profile.observe_user_message("python pytest")
    app.state.session = FakeSession(profile)

    response = TestClient(app).delete("/api/profile")

    assert response.status_code == 200
    assert response.json() == {"status": "cleared"}
    assert profile.skills == {}
    assert profile.concepts == {}
    assert profile.knowledge_gaps == []
