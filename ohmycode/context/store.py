"""SQLite storage for append-only events and derived context state."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ohmycode.context.packet import ContextPacket


@dataclass
class ContextEvent:
    id: int
    event_type: str
    content: str
    metadata: dict[str, Any]
    created_at: str


@dataclass
class Topic:
    id: str
    title: str
    summary: str = ""
    status: str = ""
    data: dict[str, Any] | None = None
    updated_at: str = ""


@dataclass
class TopicSlice:
    topic_id: str
    start_event_id: int
    end_event_id: int
    updated_at: str = ""


@dataclass
class TopicCompressionCache:
    topic_id: str
    compressed_until_event_id: int
    messages_json: str
    summary: str = ""
    updated_at: str = ""


class ContextStore:
    """Small SQLite wrapper for long-lived context data."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_dir = self.db_path.parent / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def append_event(
        self,
        event_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> int:
        created_at = created_at or _now()
        event_id = self._next_event_id()
        shard = _event_shard(created_at)
        record = {
            "event_id": event_id,
            "type": event_type,
            "content": content,
            "metadata": metadata or {},
            "created_at": created_at,
        }
        self._append_jsonl(shard, record)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO event_index(event_id, shard, created_at) VALUES (?, ?, ?)",
                (event_id, shard, created_at),
            )
            conn.execute(
                "INSERT OR REPLACE INTO curator_state(key, value) VALUES (?, ?)",
                ("next_event_id", str(event_id + 1)),
            )
        return event_id

    def list_events_after(self, event_id: int, limit: int = 100) -> list[ContextEvent]:
        rows = self._event_index_rows("event_id > ?", (event_id,), limit)
        if rows:
            return self._read_indexed_events(rows)
        return self._list_sqlite_events_after(event_id, limit)

    def list_events_range(self, start_event_id: int, end_event_id: int) -> list[ContextEvent]:
        rows = self._event_index_rows(
            "event_id BETWEEN ? AND ?",
            (start_event_id, end_event_id),
            None,
        )
        if rows:
            return self._read_indexed_events(rows)
        return [
            e for e in self._list_sqlite_events_after(start_event_id - 1, end_event_id)
            if e.id <= end_event_id
        ]

    def _list_sqlite_events_after(self, event_id: int, limit: int = 100) -> list[ContextEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, type, content, metadata_json, created_at FROM events "
                "WHERE id > ? ORDER BY id ASC LIMIT ?",
                (event_id, limit),
            ).fetchall()
        return [
            ContextEvent(
                id=row[0],
                event_type=row[1],
                content=row[2],
                metadata=json.loads(row[3] or "{}"),
                created_at=row[4],
            )
            for row in rows
        ]

    def save_topic_slices(self, topic_id: str, ranges: list[tuple[int, int]]) -> None:
        valid = [(start, end) for start, end in ranges if start > 0 and end >= start]
        with self._connect() as conn:
            conn.execute("DELETE FROM topic_slices WHERE topic_id=?", (topic_id,))
            for start, end in valid:
                conn.execute(
                    "INSERT OR IGNORE INTO topic_slices(topic_id, start_event_id, end_event_id, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (topic_id, start, end, _now()),
                )

    def list_topic_slices(self, topic_id: str) -> list[TopicSlice]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT topic_id, start_event_id, end_event_id, updated_at "
                "FROM topic_slices WHERE topic_id=? ORDER BY start_event_id ASC",
                (topic_id,),
            ).fetchall()
        return [TopicSlice(row[0], row[1], row[2], row[3]) for row in rows]

    def count_topic_slices(self, topic_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM topic_slices WHERE topic_id=?",
                (topic_id,),
            ).fetchone()
        return int(row[0] if row else 0)

    def save_compression_cache(
        self,
        topic_id: str,
        compressed_until_event_id: int,
        messages_json: str,
        summary: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO topic_compression_cache"
                "(topic_id, compressed_until_event_id, messages_json, summary, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (topic_id, compressed_until_event_id, messages_json, summary, _now()),
            )

    def load_compression_cache(self, topic_id: str) -> TopicCompressionCache | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT topic_id, compressed_until_event_id, messages_json, summary, updated_at "
                "FROM topic_compression_cache WHERE topic_id=?",
                (topic_id,),
            ).fetchone()
        if row is None:
            return None
        return TopicCompressionCache(row[0], row[1], row[2], row[3], row[4])

    def create_topic(
        self, title: str, summary: str = "", status: str = "", topic_id: str | None = None
    ) -> str:
        topic_id = topic_id or _topic_id(title)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO topics(id, title, summary, status, data_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (topic_id, title, summary, status, "{}", _now()),
            )
        return topic_id

    def update_topic(
        self,
        topic_id: str,
        title: str | None = None,
        summary: str | None = None,
        status: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        topic = self.get_topic(topic_id)
        if topic is None:
            self.create_topic(title or topic_id, summary or "", status or "", topic_id)
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE topics SET title=?, summary=?, status=?, data_json=?, updated_at=? "
                "WHERE id=?",
                (
                    title if title is not None else topic.title,
                    summary if summary is not None else topic.summary,
                    status if status is not None else topic.status,
                    json.dumps(data if data is not None else topic.data or {}),
                    _now(),
                    topic_id,
                ),
            )

    def get_topic(self, topic_id: str) -> Topic | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, summary, status, data_json, updated_at FROM topics WHERE id=?",
                (topic_id,),
            ).fetchone()
        if row is None:
            return None
        return Topic(row[0], row[1], row[2], row[3], json.loads(row[4] or "{}"), row[5])

    def list_topics(self) -> list[Topic]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, summary, status, data_json, updated_at "
                "FROM topics ORDER BY updated_at DESC"
            ).fetchall()
        return [Topic(r[0], r[1], r[2], r[3], json.loads(r[4] or "{}"), r[5]) for r in rows]

    def link_event_to_topic(self, topic_id: str, event_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO topic_events(topic_id, event_id) VALUES (?, ?)",
                (topic_id, event_id),
            )

    def save_packet(self, packet: ContextPacket) -> None:
        packet_id = packet.topic_id or "empty"
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO context_packets(id, topic_id, version, content_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (packet_id, packet.topic_id, packet.version, json.dumps(packet.to_dict()), _now()),
            )

    def load_packet(self, topic_id: str) -> ContextPacket | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content_json FROM context_packets WHERE topic_id=? ORDER BY updated_at DESC LIMIT 1",
                (topic_id,),
            ).fetchone()
        if row is None:
            return None
        return ContextPacket.from_dict(json.loads(row[0]))

    def set_state(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO curator_state(key, value) VALUES (?, ?)",
                (key, value),
            )

    def get_state(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM curator_state WHERE key=?", (key,)).fetchone()
        return default if row is None else str(row[0])

    def set_last_processed_event_id(self, event_id: int) -> None:
        self.set_state("last_processed_event_id", str(event_id))

    def get_last_processed_event_id(self) -> int:
        value = self.get_state("last_processed_event_id", "0")
        return int(value or "0")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS topics (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS topic_events (
                    topic_id TEXT NOT NULL,
                    event_id INTEGER NOT NULL,
                    PRIMARY KEY(topic_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS context_packets (
                    id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS curator_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS event_index (
                    event_id INTEGER PRIMARY KEY,
                    shard TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS topic_slices (
                    topic_id TEXT NOT NULL,
                    start_event_id INTEGER NOT NULL,
                    end_event_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(topic_id, start_event_id, end_event_id)
                );
                CREATE TABLE IF NOT EXISTS topic_compression_cache (
                    topic_id TEXT PRIMARY KEY,
                    compressed_until_event_id INTEGER NOT NULL,
                    messages_json TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _next_event_id(self) -> int:
        value = self.get_state("next_event_id", "")
        if value:
            return int(value)
        with self._connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(event_id), 0) FROM event_index").fetchone()
            old = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()
        return max(int(row[0]), int(old[0])) + 1

    def _append_jsonl(self, shard: str, record: dict[str, Any]) -> None:
        path = self.events_dir / shard
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _event_index_rows(
        self,
        where_clause: str,
        params: tuple[Any, ...],
        limit: int | None,
    ) -> list[tuple[int, str, str]]:
        limit_sql = "" if limit is None else " LIMIT ?"
        sql = (
            "SELECT event_id, shard, created_at FROM event_index WHERE "
            + where_clause
            + " ORDER BY event_id ASC"
            + limit_sql
        )
        args = params if limit is None else params + (limit,)
        with self._connect() as conn:
            return conn.execute(sql, args).fetchall()

    def _read_indexed_events(self, rows: list[tuple[int, str, str]]) -> list[ContextEvent]:
        by_id = {row[0]: row for row in rows}
        events: list[ContextEvent] = []
        for event_id in sorted(by_id):
            record = self._read_jsonl_event(event_id, by_id[event_id][1])
            if record is not None:
                events.append(record)
        return events

    def _read_jsonl_event(self, event_id: int, shard: str) -> ContextEvent | None:
        path = self.events_dir / shard
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                data = json.loads(line)
                if data.get("event_id") == event_id:
                    return ContextEvent(
                        id=event_id,
                        event_type=data.get("type", ""),
                        content=data.get("content", ""),
                        metadata=data.get("metadata") or {},
                        created_at=data.get("created_at", ""),
                    )
        return None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _event_shard(created_at: str) -> str:
    return f"{created_at[:10]}.jsonl"


def _topic_id(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return f"topic_{slug or 'default'}"
