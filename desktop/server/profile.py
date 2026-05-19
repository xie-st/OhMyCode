"""User profile v0: heuristic skill, gap, and style tracking."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

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

CORE_CONCEPTS = {
    "py.async": "Python async/await and asyncio",
    "py.errors": "Python exceptions and error handling",
    "py.testing": "Python testing and mocking",
    "py.typing": "Python type annotations and schemas",
    "se.refactor": "Software refactoring patterns",
    "se.debugging": "Systematic debugging",
    "se.trade_offs": "Engineering tradeoffs",
    "ohmycode.event_loop": "OhMyCode asyncio event loop",
    "ohmycode.tools": "OhMyCode tool execution pipeline",
}

CONCEPT_KEYWORDS = {
    "py.async": ("async", "await", "asyncio", "\u5f02\u6b65", "\u534f\u7a0b"),
    "py.errors": ("except", "raise", "error", "exception", "\u62a5\u9519"),
    "py.testing": ("pytest", "mock", "fixture", "test", "\u6d4b\u8bd5"),
    "py.typing": ("type", "annotation", "pydantic", "\u7c7b\u578b"),
    "se.refactor": ("refactor", "rename", "extract", "\u91cd\u6784"),
    "se.debugging": ("debug", "trace", "print", "\u8c03\u8bd5"),
    "se.trade_offs": ("tradeoff", "tradeoffs", "performance", "\u53d6\u820d"),
    "ohmycode.event_loop": ("event_bus", "stream_turn", "\u4e8b\u4ef6\u5faa\u73af"),
    "ohmycode.tools": ("tool_call", "tool_use", "tools/", "\u5de5\u5177"),
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
    "concepts",
    "concept_dispositions",
    "interests",
    "knowledge_gaps",
    "recent_messages",
    "interaction_style",
}

INSPIRATIONS_MAX_BYTES = 16 * 1024


@dataclass
class UserProfile:
    cwd: str
    skills: dict[str, dict[str, Any]] = field(default_factory=dict)
    concepts: dict[str, dict[str, Any]] = field(default_factory=dict)
    concept_dispositions: dict[str, str] = field(default_factory=dict)
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
            text_lc = text.lower()
            is_gap = _is_gap_text(text, text_lc)
            self._observe_skills(text_lc)
            self._observe_concepts(text, text_lc, is_gap)
            self._observe_gap(text)
            self._remember_message(text)
            self.save()

    def observe_event(self, event: StreamEvent, window: str) -> None:
        """Use Window A tool events as weak skill evidence."""
        if window != "A" or not isinstance(event, ToolCallStart):
            return
        with self._lock:
            self._observe_tool(event.tool_name.lower())
            self._observe_concepts(event.tool_name, event.tool_name.lower(), False)
            self.save()

    def snapshot_for_b(self, current_text: str = "") -> str:
        """Render a compact profile snapshot for Window B."""
        top_skills = sorted(
            self.skills.items(),
            key=lambda item: item[1].get("evidence_count", 0),
            reverse=True,
        )[:3]
        skills = _format_skills(top_skills)
        gaps = _format_gaps(self.knowledge_gaps[-2:])
        concepts = self._active_concepts_snapshot(current_text)
        avg_len = self.interaction_style.get("avg_msg_len", 0)
        style = "concise" if avg_len < 80 else "detailed"
        parts = [
            "User profile snapshot: "
            f"skills={skills}",
            f"knowledge_gaps={gaps}",
            f"interaction_style={style}",
            f"active_concepts={concepts}",
        ]
        if self.concept_dispositions:
            dispositions = ", ".join(
                f"{key}={value}"
                for key, value in sorted(self.concept_dispositions.items())
            )
            parts.append(f"dispositions: {dispositions}")
        return "; ".join(parts)

    def load_inspirations(self) -> str:
        """Load project and global inspiration markdown with a small cap."""
        roots = [
            _project_root(self.cwd) / "inspirations",
            Path.home() / ".ohmycode" / "inspirations",
        ]
        chunks: list[str] = []
        remaining = INSPIRATIONS_MAX_BYTES
        for root in roots:
            if remaining <= 0 or not root.exists():
                continue
            for path in sorted(root.glob("*.md")):
                if remaining <= 0:
                    break
                try:
                    data = path.read_bytes()[:remaining]
                except OSError:
                    continue
                text = data.decode("utf-8", errors="replace").strip()
                if text:
                    chunks.append(f"### {path.name}\n{text}")
                    remaining -= len(data)
        return "\n\n".join(chunks)

    def delete_evidence(self, evidence_id: str) -> bool:
        deleted = False
        with self._lock:
            for concept in self.concepts.values():
                evidence = concept.get("evidence", [])
                kept = [item for item in evidence if item.get("id") != evidence_id]
                if len(kept) != len(evidence):
                    concept["evidence"] = kept
                    _recompute_concept(concept)
                    deleted = True
            kept_gaps = [
                gap for gap in self.knowledge_gaps if gap.get("id") != evidence_id
            ]
            if len(kept_gaps) != len(self.knowledge_gaps):
                self.knowledge_gaps = kept_gaps
                deleted = True
            if deleted:
                self.save()
        return deleted

    def clear(self) -> None:
        with self._lock:
            self.skills = {}
            self.concepts = {}
            self.concept_dispositions = {}
            self.interests = []
            self.knowledge_gaps = []
            self.recent_messages = []
            self.interaction_style = {}
            self.save()

    def save(self) -> None:
        """Persist atomically: write a uniquely-named sibling then replace.

        Falls back to direct write if os.replace hits a Windows file-lock
        race (antivirus / indexer briefly holds the target during rapid
        successive writes — observed under pytest's 25-message loop).
        """
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._to_json_data(), ensure_ascii=False, indent=2)
        tmp_path = self._path.with_suffix(
            f".tmp.{os.getpid()}.{time.time_ns()}"
        )
        tmp_path.write_text(payload, encoding="utf-8")
        try:
            os.replace(tmp_path, self._path)
        except PermissionError:
            self._path.write_text(payload, encoding="utf-8")
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass

    def _observe_skills(self, text_lc: str) -> None:
        for skill, keywords in KEYWORD_SKILLS.items():
            hit_count = sum(text_lc.count(keyword) for keyword in keywords)
            if hit_count:
                _bump_skill(self.skills, skill, hit_count)

    def _observe_tool(self, tool_name: str) -> None:
        for skill, keywords in KEYWORD_SKILLS.items():
            if any(keyword in tool_name for keyword in keywords):
                _bump_skill(self.skills, skill, 1)

    def _observe_concepts(self, context: str, text_lc: str, is_gap: bool) -> None:
        for concept_id, keywords in CONCEPT_KEYWORDS.items():
            if any(keyword in text_lc for keyword in keywords):
                _add_concept_evidence(self.concepts, concept_id, context, is_gap)

    def _observe_gap(self, text: str) -> None:
        text_lc = text.lower()
        if _is_gap_text(text, text_lc):
            self.knowledge_gaps.append(
                {"id": uuid4().hex, "text": text[:120], "ts": _now_iso()}
            )
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
            "concepts": self.concepts,
            "concept_dispositions": self.concept_dispositions,
            "interests": self.interests,
            "knowledge_gaps": self.knowledge_gaps,
            "recent_messages": self.recent_messages,
            "interaction_style": self.interaction_style,
        }

    def _active_concepts_snapshot(self, current_text: str) -> str:
        text_lc = current_text.lower()
        active_concepts = []
        for concept_id, keywords in CONCEPT_KEYWORDS.items():
            if concept_id not in self.concepts:
                continue
            if any(keyword in text_lc for keyword in keywords):
                level = self.concepts[concept_id].get("level", 0)
                active_concepts.append(f"{concept_id}(lvl {level})")
        return ", ".join(active_concepts) or "(none active)"


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


def _add_concept_evidence(
    concepts: dict[str, dict[str, Any]], concept_id: str, context: str, is_gap: bool
) -> None:
    entry = concepts.setdefault(
        concept_id,
        {"level": 0, "evidence_count": 0, "last_seen": "", "evidence_ids": []},
    )
    evidence = entry.setdefault("evidence", [])
    item = {
        "id": uuid4().hex,
        "ts": _now_iso(),
        "context": context[:100],
        "is_gap": is_gap,
    }
    evidence.append(item)
    entry["evidence"] = evidence[-50:]
    _recompute_concept(entry)


def _recompute_concept(entry: dict[str, Any]) -> None:
    evidence = entry.get("evidence", [])[-50:]
    clean_count = sum(1 for item in evidence if not item.get("is_gap", False))
    if clean_count >= 5:
        level = 2
    elif clean_count >= 3:
        level = 1
    else:
        level = 0
    entry["evidence"] = evidence
    entry["evidence_count"] = len(evidence)
    entry["level"] = level
    entry["evidence_ids"] = [item.get("id", "") for item in evidence if item.get("id")]
    entry["last_seen"] = evidence[-1].get("ts", "") if evidence else ""


def _is_gap_text(text: str, text_lc: str) -> bool:
    return any(trigger in text_lc or trigger in text for trigger in GAP_TRIGGERS)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    return _project_root(cwd) / "profile" / "profile.json"


def _project_root(cwd: str) -> Path:
    root = _canonical_project_root(_find_git_root(cwd) or os.path.abspath(cwd))
    slug = _sanitize_slug(root)
    return Path.home() / ".ohmycode" / "projects" / slug
