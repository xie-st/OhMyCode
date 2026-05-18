import pytest

from desktop.server.profile import UserProfile


@pytest.fixture
def profile(tmp_path, monkeypatch):
    target = tmp_path / "profile.json"
    monkeypatch.setattr("desktop.server.profile._profile_path", lambda cwd: target)
    return UserProfile.for_cwd("/tmp/fake")


def test_concept_keyword_hit_creates_evidence(profile):
    profile.observe_user_message("请解释 async 怎么用")

    concept = profile.concepts["py.async"]
    assert concept["evidence_count"] == 1
    assert concept["level"] == 0
    assert len(concept["evidence"]) == 1
    assert concept["evidence"][0]["id"]
    assert concept["evidence"][0]["is_gap"] is False


def test_concept_levels_up_after_3_clean_evidences(profile):
    for index in range(3):
        profile.observe_user_message(f"async await asyncio example {index}")

    assert profile.concepts["py.async"]["level"] == 1


def test_concept_gap_does_not_level_up(profile):
    for index in range(3):
        profile.observe_user_message(f"为什么 async await asyncio confusing {index}")

    concept = profile.concepts["py.async"]
    assert concept["evidence_count"] == 3
    assert concept["level"] == 0
    assert all(item["is_gap"] for item in concept["evidence"])


def test_concept_level_caps_at_2(profile):
    for index in range(12):
        profile.observe_user_message(f"pytest mock fixture test {index}")

    assert profile.concepts["py.testing"]["level"] == 2


def test_active_concepts_in_snapshot(profile):
    profile.observe_user_message("pytest mock fixture test")

    snapshot = profile.snapshot_for_b(current_text="please add a pytest mock")

    assert "active_concepts=py.testing(lvl 0)" in snapshot
