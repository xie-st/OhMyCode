"""Memory system (Task 17) — MEMORY.md index and LLM extraction."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# ---- Paths ----

MEMORY_DIR = Path.home() / ".ohmycode" / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"


# ---- Helpers ----


def ensure_memory_dir() -> None:
    """Create the memory directory if it doesn't exist."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def load_memory_index() -> str:
    """Read and return the contents of MEMORY.md, or empty string if missing."""
    ensure_memory_dir()
    if MEMORY_INDEX.exists():
        return MEMORY_INDEX.read_text(encoding="utf-8")
    return ""


def _build_index() -> str:
    """Rebuild MEMORY.md from all .md files in the memory directory."""
    lines = ["# OhMyCode Memory Index\n"]
    for md_file in sorted(MEMORY_DIR.glob("*.md")):
        if md_file.name == "MEMORY.md":
            continue
        try:
            raw = md_file.read_text(encoding="utf-8")
            name, mem_type = _parse_frontmatter_meta(raw)
            lines.append(f"- [{name}]({md_file.name}) type={mem_type}\n")
        except Exception:
            pass
    return "".join(lines)


def _parse_frontmatter_meta(content: str) -> tuple[str, str]:
    """Extract name and type from frontmatter block."""
    name = "unknown"
    mem_type = "general"
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            frontmatter = content[3:end]
            for line in frontmatter.splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("type:"):
                    mem_type = line.split(":", 1)[1].strip()
    return name, mem_type


def save_memory(name: str, memory_type: str, content: str) -> str:
    """Write a memory to a .md file with frontmatter and update MEMORY.md index.

    Returns the filename of the saved memory.
    """
    ensure_memory_dir()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    # Sanitize name for filename
    safe_name = re.sub(r"[^\w\-]", "_", name)[:40]
    filename = f"{timestamp}-{safe_name}.md"
    filepath = MEMORY_DIR / filename
    frontmatter = f"---\nname: {name}\ntype: {memory_type}\ncreated: {timestamp}\n---\n\n"
    filepath.write_text(frontmatter + content, encoding="utf-8")
    # Rebuild index
    MEMORY_INDEX.write_text(_build_index(), encoding="utf-8")
    return filename


def delete_memory(filename: str) -> bool:
    """Delete a memory file and remove it from the index.

    Returns True if deleted, False if not found.
    """
    ensure_memory_dir()
    filepath = MEMORY_DIR / filename
    if not filepath.exists():
        return False
    filepath.unlink()
    # Rebuild index
    MEMORY_INDEX.write_text(_build_index(), encoding="utf-8")
    return True


def list_memories() -> List[dict]:
    """Parse all .md memory files and return a list of dicts with name, type, filename."""
    ensure_memory_dir()
    results = []
    for md_file in sorted(MEMORY_DIR.glob("*.md")):
        if md_file.name == "MEMORY.md":
            continue
        try:
            raw = md_file.read_text(encoding="utf-8")
            name, mem_type = _parse_frontmatter_meta(raw)
            results.append({"name": name, "type": mem_type, "filename": md_file.name})
        except Exception:
            pass
    return results


async def extract_memories_from_conversation(
    messages: list,
    provider,
    model: str,
) -> List[dict]:
    """Use LLM to extract memorable facts from the conversation.

    Returns a list of dicts: [{name, type, content}].
    Fails silently (returns empty list on error).
    """
    try:
        from ohmycode.core.messages import UserMessage

        conversation_text = "\n".join(
            f"{getattr(m, 'role', 'user')}: {getattr(m, 'content', '')}"
            for m in messages
        )
        prompt = (
            "Analyze this conversation and extract key facts worth remembering. "
            "For each memory, output a JSON object on its own line with keys: "
            '"name" (short label), "type" (one of: fact, preference, context, task), "content" (1-2 sentences). '
            "Output ONLY JSON lines, no other text.\n\n"
            f"{conversation_text}"
        )
        request = [UserMessage(content=prompt)]
        result = await provider.complete(
            messages=request,
            model=model,
            system_prompt="You are a helpful assistant that extracts memorable facts from conversations.",
            tools=[],
        )
        raw_text = result.content if hasattr(result, "content") else str(result)
        memories = []
        import json

        for line in raw_text.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    obj = json.loads(line)
                    if "name" in obj and "type" in obj and "content" in obj:
                        memories.append(obj)
                except json.JSONDecodeError:
                    pass
        return memories
    except Exception:
        return []
