"""User profile v0: heuristic skill, gap, and style tracking."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ohmycode.core.messages import StreamEvent, ToolCallStart
from ohmycode.memory.backend import (
    _canonical_project_root,
    _find_git_root,
    _sanitize_slug,
)


KEYWORD_SKILLS = {
    "python": ["python", "py", "asyncio", "pytest", "fastapi", "pydantic"],
    "react": ["react", "jsx", "tsx", "hook", "zustand", "vite"],
    "sql": ["sql", "select", "join", "query", "where"],
    "git": ["git", "commit", "branch", "rebase", "merge"],
    "testing": ["test", "tests", "pytest", "fixture", "mock"],
    "async": ["async", "await", "asyncio", "websocket"],
    "frontend": ["css", "tailwind", "component", "layout", "ui"],
    "backend": ["api", "server", "fastapi", "endpoint", "websocket"],
}

GAP_TRIGGERS = (
    "\u4e0d\u61c2",
    "\u4e0d\u4f1a",
    "\u4e3a\u4ec0\u4e48",
    "\u770b\u4e0d\u61c2",
    "\u4e0d\u7406\u89e3",
    "confused",
    "do not understand",
    "don't understand",
    "why",
    "what does",
)

PROFILE_FIELDS = {
    "cwd",
    "skills",
    "interests",
    "knowledge_gaps",
    "recent_messages",
    "interaction_style",
}


@dataclass
class UserProfile:
    cwd: str
    skills: dict[str, dict[str, Any]] = field(default_factory=dict)
    interests: list[str] = field(default_factory=list)
    knowledge_gaps: list[dict[str, str]] = field(default_factory=list)
    recent_messages: list[str] = field(default_factory=list)
    interaction_style: dict[str, Any] = field(default_factory=dict)

    _path: Path | None = field(default=None, init=False, repr=False, compare=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False, compare=False
    )

    @classmethod
    def for_cwd(cls, cwd: str) -> "UserProfile":
        path = _profile_path(cwd)
        profile = cls(cwd=cwd)
        if path.exists():
            profile = _load_profile(path, cwd)
        profile._path = path
        return profile

    def observe_user_message(self, text: str) -> None:
        """Capture a user message and persist the updated profile."""
        with self._lock:
            self._observe_skills(text.lower())
            self._observe_gap(text)
            self._remember_message(text)
            self.save()

    def observe_event(self, event: StreamEvent, window: str) -> None:
        """Use Window A tool events as weak skill evidence."""
        if window != "A" or not isinstance(event, ToolCallStart):
            return
        with self._lock:
            self._observe_tool(event.tool_name.lower())
            self.save()

    def snapshot_for_b(self) -> str:
        """Render a compact profile snapshot for Window B."""
        top_skills = sorted(
            self.skills.items(),
            key=lambda item: item[1].get("evidence_count", 0),
            reverse=True,
        )[:3]
        skills = _format_skills(top_skills)
        gaps = _format_gaps(self.knowledge_gaps[-2:])
        avg_len = self.interaction_style.get("avg_msg_len", 0)
        style = "concise" if avg_len < 80 else "detailed"
        return (
            "User profile snapshot: "
            f"skills={skills}; knowledge_gaps={gaps}; interaction_style={style}"
        )

    def save(self) -> None:
        """Persist with tempfile + os.replace so readers never see partial JSON."""
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = self._to_json_data()
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self._path.parent, delete=False, suffix=".tmp"
        ) as temp_file:
            json.dump(data, temp_file, ensure_ascii=False, indent=2)
            tmp_name = temp_file.name
        os.replace(tmp_name, self._path)

    def _observe_skills(self, text_lc: str) -> None:
        for skill, keywords in KEYWORD_SKILLS.items():
            hit_count = sum(text_lc.count(keyword) for keyword in keywords)
            if hit_count:
                _bump_skill(self.skills, skill, hit_count)

    def _observe_tool(self, tool_name: str) -> None:
        for skill, keywords in KEYWORD_SKILLS.items():
            if any(keyword in tool_name for keyword in keywords):
                _bump_skill(self.skills, skill, 1)

    def _observe_gap(self, text: str) -> None:
        text_lc = text.lower()
        if any(trigger in text_lc or trigger in text for trigger in GAP_TRIGGERS):
            self.knowledge_gaps.append({"text": text[:120]})
            self.knowledge_gaps = self.knowledge_gaps[-30:]

    def _remember_message(self, text: str) -> None:
        self.recent_messages.append(text[:200])
        self.recent_messages = self.recent_messages[-20:]
        lengths = [len(message) for message in self.recent_messages]
        self.interaction_style["avg_msg_len"] = sum(lengths) / max(1, len(lengths))

    def _to_json_data(self) -> dict[str, Any]:
        return {
            "cwd": self.cwd,
            "skills": self.skills,
            "interests": self.interests,
            "knowledge_gaps": self.knowledge_gaps,
            "recent_messages": self.recent_messages,
            "interaction_style": self.interaction_style,
        }


def _load_profile(path: Path, fallback_cwd: str) -> UserProfile:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = {key: value for key, value in data.items() if key in PROFILE_FIELDS}
        fields.setdefault("cwd", fallback_cwd)
        return UserProfile(**fields)
    except Exception:
        return UserProfile(cwd=fallback_cwd)


def _bump_skill(skills: dict[str, dict[str, Any]], skill: str, count: int) -> None:
    entry = skills.setdefault(skill, {"level": 0.0, "evidence_count": 0})
    entry["evidence_count"] = entry.get("evidence_count", 0) + count
    entry["level"] = min(2.0, entry.get("level", 0.0) + 0.1 * count)


def _format_skills(top_skills: list[tuple[str, dict[str, Any]]]) -> str:
    if not top_skills:
        return "none yet"
    return ", ".join(
        f"{name}(lvl {round(details.get('level', 0.0), 1)})"
        for name, details in top_skills
    )


def _format_gaps(gaps: list[dict[str, str]]) -> str:
    if not gaps:
        return "none yet"
    return ", ".join(gap.get("text", "")[:30] for gap in gaps)


def _profile_path(cwd: str) -> Path:
    root = _canonical_project_root(_find_git_root(cwd) or os.path.abspath(cwd))
    slug = _sanitize_slug(root)
    return Path.home() / ".ohmycode" / "projects" / slug / "profile" / "profile.json"
