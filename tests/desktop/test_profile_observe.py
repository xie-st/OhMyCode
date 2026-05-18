import json

import pytest

from desktop.server.profile import UserProfile


@pytest.fixture
def profile(tmp_path, monkeypatch):
    target = tmp_path / "profile.json"
    monkeypatch.setattr("desktop.server.profile._profile_path", lambda cwd: target)
    return UserProfile.for_cwd("/tmp/fake")


def test_observe_user_message_counts_python_skill(profile):
    profile.observe_user_message("I am using python asyncio with pytest")

    assert "python" in profile.skills
    assert profile.skills["python"]["evidence_count"] >= 3


def test_observe_user_message_captures_gap(profile):
    profile.observe_user_message("I do not understand why this SQL join fails")

    assert len(profile.knowledge_gaps) == 1
    assert "SQL join" in profile.knowledge_gaps[0]["text"]


def test_observe_user_message_persists(profile, tmp_path):
    profile.observe_user_message("Hello world")

    target = tmp_path / "profile.json"
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["recent_messages"] == ["Hello world"]


def test_snapshot_for_b_handles_empty_profile(profile):
    snap = profile.snapshot_for_b()

    assert "User profile snapshot" in snap
    assert "none yet" in snap


def test_snapshot_for_b_includes_top_skills(profile):
    profile.observe_user_message("python asyncio and pytest with fastapi")

    snap = profile.snapshot_for_b()

    assert "python" in snap


def test_recent_messages_caps_at_20(profile):
    for index in range(25):
        profile.observe_user_message(f"message {index}")

    assert len(profile.recent_messages) == 20
    assert profile.recent_messages[0] == "message 5"
