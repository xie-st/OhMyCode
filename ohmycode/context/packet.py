"""Context packet rendering for the foreground agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextPacket:
    """Stable working context injected into the current model turn."""

    topic_id: str = ""
    title: str = ""
    summary: str = ""
    status: str = ""
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    related_topics: list[str] = field(default_factory=list)
    global_memory: list[str] = field(default_factory=list)
    version: int = 1
    last_event_id: int = 0

    @classmethod
    def empty(cls) -> "ContextPacket":
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextPacket":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in allowed})

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "title": self.title,
            "summary": self.summary,
            "status": self.status,
            "decisions": self.decisions,
            "open_questions": self.open_questions,
            "next_actions": self.next_actions,
            "related_files": self.related_files,
            "related_topics": self.related_topics,
            "global_memory": self.global_memory,
            "version": self.version,
            "last_event_id": self.last_event_id,
        }

    def render(self, max_chars: int = 24_000) -> str:
        if not self.topic_id:
            return (
                "# Current Working Context\n"
                "No active long-term topic yet. Use the current user message and "
                "short-term conversation history.\n"
            )[:max_chars]

        sections = [
            "# Current Working Context",
            f"Active topic: {self.title or self.topic_id}",
            f"topic_id: {self.topic_id}",
            f"version: {self.version}",
        ]
        if self.status:
            sections.append(f"Status: {self.status}")
        if self.summary:
            sections.append(f"Summary: {self.summary}")
        self._append_list(sections, "Decisions", self.decisions)
        self._append_list(sections, "Open Questions", self.open_questions)
        self._append_list(sections, "Next Actions", self.next_actions)
        self._append_list(sections, "Related Files", self.related_files)

        rendered = "\n".join(sections) + "\n"
        for label, items in (
            ("Related Topics", self.related_topics),
            ("Relevant Memory", self.global_memory),
        ):
            candidate = rendered + self._format_list(label, items)
            if len(candidate) <= max_chars:
                rendered = candidate

        if len(rendered) > max_chars:
            rendered = rendered[: max(0, max_chars - 20)].rstrip() + "\n...[truncated]\n"
        return rendered

    @staticmethod
    def _append_list(sections: list[str], label: str, items: list[str]) -> None:
        if items:
            sections.append(ContextPacket._format_list(label, items).rstrip())

    @staticmethod
    def _format_list(label: str, items: list[str]) -> str:
        if not items:
            return ""
        lines = [f"{label}:"]
        lines.extend(f"- {item}" for item in items)
        return "\n".join(lines) + "\n"

