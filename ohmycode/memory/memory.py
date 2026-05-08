"""Backwards-compatible re-exports.

The memory subsystem now lives in three focused modules:
  - ``backend.py``       — protocol + registry + project-dir resolution
  - ``btree_backend.py`` — the default ``BTreeMemoryStore`` implementation
  - ``extraction.py``    — LLM-driven extraction of memories from a conversation

This module is kept as a shim so existing imports (``from
ohmycode.memory.memory import BTreeMemoryStore, ...``) continue to work.
New code should import from the focused modules directly.
"""

from __future__ import annotations

from ohmycode.memory.backend import (
    MemoryBackend,
    auto_import_memory_backends,
    get_memory_backend,
    get_project_memory_dir,
    register_memory_backend,
)
from ohmycode.memory.btree_backend import (
    MAX_INDEX_BYTES,
    MAX_INDEX_LINES,
    VALID_CATEGORIES,
    BTreeMemoryStore,
    _parse_frontmatter_meta,
)
from ohmycode.memory.extraction import (
    _EXTRACTION_SYSTEM,
    _build_extraction_request,
    extract_memories_from_conversation,
    extract_memories_with_box,
    extract_memories_with_box_cancellable,
    filter_messages_for_extraction,
    parse_extraction_response,
)

__all__ = [
    "BTreeMemoryStore",
    "MAX_INDEX_BYTES",
    "MAX_INDEX_LINES",
    "MemoryBackend",
    "VALID_CATEGORIES",
    "_EXTRACTION_SYSTEM",
    "_build_extraction_request",
    "_parse_frontmatter_meta",
    "auto_import_memory_backends",
    "extract_memories_from_conversation",
    "extract_memories_with_box",
    "extract_memories_with_box_cancellable",
    "filter_messages_for_extraction",
    "get_memory_backend",
    "get_project_memory_dir",
    "parse_extraction_response",
    "register_memory_backend",
]
