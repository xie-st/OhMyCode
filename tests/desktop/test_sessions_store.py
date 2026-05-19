import json

from desktop.server.sessions import SessionStore


def test_create_new_writes_session_directory_and_json_files(tmp_path):
    store = SessionStore(root=tmp_path)

    session = store.create_new("project-one", title="New chat")

    session_dir = tmp_path / "project-one" / "sessions" / session.id
    assert session_dir.is_dir()
    assert (session_dir / "meta.json").exists()
    assert json.loads((session_dir / "a-messages.json").read_text()) == []
    assert json.loads((session_dir / "b-messages.json").read_text()) == []
    assert session.title == "New chat"
    assert session.project_slug == "project-one"


def test_list_sessions_returns_updated_at_descending(tmp_path):
    store = SessionStore(root=tmp_path)
    older = store.create_new("project-one", title="Older")
    newer = store.create_new("project-one", title="Newer")
    store._write_meta(older, updated_at="2026-01-01T00:00:00+00:00")
    store._write_meta(newer, updated_at="2026-01-02T00:00:00+00:00")

    sessions = store.list_sessions("project-one")

    assert [session.id for session in sessions] == [newer.id, older.id]


def test_save_and_load_messages_by_window(tmp_path):
    store = SessionStore(root=tmp_path)
    session = store.create_new("project-one")
    messages = [{"role": "user", "text": "hello"}]

    store.save_messages("project-one", session.id, "A", messages)

    assert store.load_messages("project-one", session.id, "A") == messages
    assert store.load_messages("project-one", session.id, "B") == []


def test_save_messages_refreshes_updated_at(tmp_path):
    store = SessionStore(root=tmp_path)
    session = store.create_new("project-one")
    store._write_meta(session, updated_at="2026-01-01T00:00:00+00:00")

    store.save_messages("project-one", session.id, "B", [{"role": "assistant", "text": "x"}])

    [saved] = store.list_sessions("project-one")
    assert saved.updated_at != "2026-01-01T00:00:00+00:00"


def test_update_title_changes_meta(tmp_path):
    store = SessionStore(root=tmp_path)
    session = store.create_new("project-one", title="Before")

    store.update_title("project-one", session.id, "After")

    [saved] = store.list_sessions("project-one")
    assert saved.title == "After"


def test_delete_removes_session_directory(tmp_path):
    store = SessionStore(root=tmp_path)
    session = store.create_new("project-one")

    store.delete("project-one", session.id)

    assert store.list_sessions("project-one") == []
