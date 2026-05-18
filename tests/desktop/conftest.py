import pytest


@pytest.fixture(autouse=True)
def isolate_desktop_profile_path(tmp_path, monkeypatch):
    target = tmp_path / "profile.json"
    monkeypatch.setattr("desktop.server.profile._profile_path", lambda cwd: target)
