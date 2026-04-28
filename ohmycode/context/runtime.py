"""Foreground context runtime owned by the REPL."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

from ohmycode.context.packet import ContextPacket
from ohmycode.context.store import ContextStore, Topic
from ohmycode.memory.memory import get_project_memory_dir


@dataclass
class RouteDecision:
    action: str
    topic_id: str = ""
    candidates: list[str] = field(default_factory=list)


@dataclass
class PreparedContext:
    system_prompt: str
    packet: ContextPacket
    route: RouteDecision


class ContextRuntime:
    """Coordinates topic routing, packet caching, and curator scheduling."""

    def __init__(self, store: ContextStore) -> None:
        self.store = store
        self._curator_task: asyncio.Task | None = None
        self._curator_pending = False
        self._compression_tasks: dict[str, asyncio.Task] = {}
        self._compression_pending: set[str] = set()

    @classmethod
    def for_cwd(cls, cwd: str) -> "ContextRuntime":
        memory_dir = Path(get_project_memory_dir(cwd))
        db_path = memory_dir.parent / "context" / "context.db"
        return cls(ContextStore(db_path))

    def record_user_message(self, content: str) -> int:
        return self.store.append_event("user_message", content)

    def record_assistant_message(
        self,
        content: str,
        tool_calls: list[dict] | None = None,
    ) -> int:
        metadata = {"tool_calls": tool_calls or []}
        return self.store.append_event("assistant_message", content, metadata)

    def record_tool_call(self, tool_name: str, content: str) -> int:
        return self.store.append_event("tool_call", content, {"tool_name": tool_name})

    def record_tool_result(self, tool_use_id: str, content: str, is_error: bool) -> int:
        return self.store.append_event(
            "tool_result", content, {"tool_use_id": tool_use_id, "is_error": is_error}
        )

    def record_turn_complete(self, finish_reason: str) -> int:
        return self.store.append_event("turn_complete", finish_reason)

    def prepare_for_turn(
        self, user_text: str, base_system_prompt: str, last_event_id: int = 0
    ) -> PreparedContext:
        route = self._route(user_text)
        packet = self._packet_for_route(route, user_text, last_event_id)
        prompt = base_system_prompt.rstrip() + "\n\n" + packet.render()
        return PreparedContext(system_prompt=prompt, packet=packet, route=route)

    @property
    def curator_pending(self) -> bool:
        return self._curator_pending

    @property
    def curator_running(self) -> bool:
        return self._curator_task is not None and not self._curator_task.done()

    def request_curator_run(self, run_coro_factory) -> asyncio.Task:
        if self._curator_task and not self._curator_task.done():
            self._curator_pending = True
            return self._curator_task

        async def _runner() -> None:
            while True:
                pending_before_run = self._curator_pending
                self._curator_pending = False
                try:
                    await run_coro_factory()
                except Exception:
                    return
                if not self._curator_pending and not pending_before_run:
                    return

        self._curator_task = asyncio.create_task(_runner())
        return self._curator_task

    def request_topic_compression(self, topic_id: str, run_coro_factory) -> asyncio.Task:
        task = self._compression_tasks.get(topic_id)
        if task is not None and not task.done():
            self._compression_pending.add(topic_id)
            return task

        async def _runner() -> None:
            while True:
                pending_before_run = topic_id in self._compression_pending
                self._compression_pending.discard(topic_id)
                try:
                    await run_coro_factory()
                except Exception:
                    return
                if topic_id not in self._compression_pending and not pending_before_run:
                    return

        task = asyncio.create_task(_runner())
        self._compression_tasks[topic_id] = task
        return task

    async def close(self, timeout: float = 1.0) -> None:
        if self._curator_task and not self._curator_task.done():
            try:
                await asyncio.wait_for(self._curator_task, timeout=timeout)
            except asyncio.TimeoutError:
                self._curator_task.cancel()
                try:
                    await self._curator_task
                except asyncio.CancelledError:
                    pass
        for task in list(self._compression_tasks.values()):
            if task.done():
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def switch_topic(self, topic_id: str) -> bool:
        if self.store.get_topic(topic_id) is None:
            return False
        self.store.set_state("active_topic_id", topic_id)
        self.store.append_event(
            "context_correction", f"Switched active topic to {topic_id}", {"topic_id": topic_id}
        )
        return True

    def get_active_packet(self) -> ContextPacket:
        active_topic_id = self.store.get_state("active_topic_id", "")
        if not active_topic_id:
            return ContextPacket.empty()
        packet = self.store.load_packet(active_topic_id)
        return packet or self._new_packet_from_topic(active_topic_id)

    def _route(self, user_text: str) -> RouteDecision:
        topics = self.store.list_topics()
        active_topic_id = self.store.get_state("active_topic_id", "")
        if not topics:
            return RouteDecision("new_topic")

        scored = [(self._score(user_text, topic), topic.id) for topic in topics]
        scored = [item for item in scored if item[0] > 0]
        scored.sort(reverse=True)
        if len(scored) >= 2 and scored[0][0] == scored[1][0]:
            return RouteDecision("ambiguous", candidates=[scored[0][1], scored[1][1]])
        if scored:
            best_id = scored[0][1]
            if best_id == active_topic_id:
                return RouteDecision("patch", topic_id=best_id)
            return RouteDecision("switch", topic_id=best_id)
        if active_topic_id:
            return RouteDecision("keep", topic_id=active_topic_id)
        return RouteDecision("new_topic")

    def _packet_for_route(
        self, route: RouteDecision, user_text: str, last_event_id: int
    ) -> ContextPacket:
        if route.action == "new_topic":
            topic_id = self.store.create_topic(_title_from_text(user_text), summary=user_text)
            self.store.set_state("active_topic_id", topic_id)
            packet = self._new_packet_from_topic(topic_id, last_event_id)
            self.store.save_packet(packet)
            return packet
        topic_id = route.topic_id or self.store.get_state("active_topic_id", "")
        if route.action in ("switch", "patch"):
            self.store.set_state("active_topic_id", topic_id)
        packet = self.store.load_packet(topic_id) or self._new_packet_from_topic(topic_id)
        if route.action == "patch":
            packet.version += 1
            packet.last_event_id = last_event_id
            self.store.save_packet(packet)
        return packet

    def _new_packet_from_topic(self, topic_id: str, last_event_id: int = 0) -> ContextPacket:
        topic = self.store.get_topic(topic_id)
        if topic is None:
            return ContextPacket.empty()
        return ContextPacket(
            topic_id=topic.id,
            title=topic.title,
            summary=topic.summary,
            status=topic.status,
            version=1,
            last_event_id=last_event_id,
        )

    @staticmethod
    def _score(user_text: str, topic: Topic) -> int:
        query = _tokens(user_text)
        haystack = _tokens(f"{topic.title} {topic.summary}")
        return len(query & haystack)


def _tokens(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "how", "what", "should", "please"}
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in stop}


def _title_from_text(text: str) -> str:
    tokens = list(_tokens(text))
    if not tokens:
        return "general"
    return " ".join(tokens[:4])
