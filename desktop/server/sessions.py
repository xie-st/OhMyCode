"""Session persistence for desktop windows.

Each session is a directory:
    ~/.ohmycode/projects/<slug>/sessions/<session_id>/
        meta.json
        a-messages.json
        b-messages.json
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ohmycode.memory.backend import (
    _canonical_project_root,
    _find_git_root,
    _sanitize_slug,
)


WindowId = Literal["A", "B"]


@dataclass
class Session:
    id: str
    title: str
    created_at: str
    updated_at: str
    project_slug: str


class SessionStore:
    """JSON-backed desktop session store."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.home() / ".ohmycode" / "projects"

    def list_sessions(self, slug: str) -> list[Session]:
        sessions_dir = self._sessions_dir(slug)
        if not sessions_dir.exists():
            return []
        sessions = []
        for path in sessions_dir.iterdir():
            if not path.is_dir():
                continue
            session = self._read_meta(path / "meta.json")
            if session is not None:
                sessions.append(session)
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    def load_messages(self, slug: str, session_id: str, window: WindowId) -> list[dict]:
        path = self._messages_path(slug, session_id, window)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def save_messages(
        self, slug: str, session_id: str, window: WindowId, messages: list[dict]
    ) -> None:
        session_dir = self._session_dir(slug, session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self._messages_path(slug, session_id, window), messages)
        meta = self._read_meta(session_dir / "meta.json")
        if meta is None:
            now = _now_iso()
            meta = Session(session_id, "New conversation", now, now, slug)
        self._write_meta(meta, updated_at=_now_iso())

    def create_new(self, slug: str, title: str = "New conversation") -> Session:
        now = _now_iso()
        session = Session(
            id=_new_session_id(),
            title=title,
            created_at=now,
            updated_at=now,
            project_slug=slug,
        )
        session_dir = self._session_dir(slug, session.id)
        session_dir.mkdir(parents=True, exist_ok=False)
        self._write_meta(session)
        self._write_json(session_dir / "a-messages.json", [])
        self._write_json(session_dir / "b-messages.json", [])
        return session

    def delete(self, slug: str, session_id: str) -> None:
        session_dir = self._session_dir(slug, session_id)
        if session_dir.exists():
            shutil.rmtree(session_dir)

    def update_title(self, slug: str, session_id: str, title: str) -> None:
        session_dir = self._session_dir(slug, session_id)
        meta = self._read_meta(session_dir / "meta.json")
        if meta is None:
            return
        meta.title = title
        self._write_meta(meta, updated_at=_now_iso())

    def _sessions_dir(self, slug: str) -> Path:
        return self.root / slug / "sessions"

    def _session_dir(self, slug: str, session_id: str) -> Path:
        return self._sessions_dir(slug) / session_id

    def _messages_path(self, slug: str, session_id: str, window: WindowId) -> Path:
        prefix = "a" if window == "A" else "b"
        return self._session_dir(slug, session_id) / f"{prefix}-messages.json"

    def _read_meta(self, path: Path) -> Session | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Session(
                id=str(data["id"]),
                title=str(data.get("title") or "New conversation"),
                created_at=str(data["created_at"]),
                updated_at=str(data["updated_at"]),
                project_slug=str(data["project_slug"]),
            )
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _write_meta(self, session: Session, updated_at: str | None = None) -> None:
        if updated_at is not None:
            session.updated_at = updated_at
        path = self._session_dir(session.project_slug, session.id) / "meta.json"
        self._write_json(path, asdict(session))

    def _write_json(self, path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def project_slug_for_cwd(cwd: str | None = None) -> str:
    resolved_cwd = cwd or os.getcwd()
    root = _canonical_project_root(
        _find_git_root(resolved_cwd) or os.path.abspath(resolved_cwd)
    )
    return _sanitize_slug(root)


def _new_session_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


sessions_store = SessionStore()
