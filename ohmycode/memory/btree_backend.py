"""B+-Tree-inspired hierarchical memory store.

Three-level layout:
  L0 (root)     — INDEX.md: compact per-category summary, always in system prompt
  L1 (internal) — _SUMMARY.md per category: entry list with one-line descriptions
  L2 (leaf)     — individual .md files with frontmatter + full content
"""

from __future__ import annotations

import logging
import random
import re
import string
from datetime import datetime
from pathlib import Path

from ohmycode.memory.backend import register_memory_backend

logger = logging.getLogger(__name__)

MAX_INDEX_LINES = 30
MAX_INDEX_BYTES = 4096
VALID_CATEGORIES = ("user", "feedback", "project", "reference")


def _parse_frontmatter_meta(content: str) -> tuple[str, str]:
    """Extract name and type from a leaf file's frontmatter block."""
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


class BTreeMemoryStore:
    """Three-level B+-Tree-inspired memory store."""

    def __init__(self, memory_dir: Path | str):
        self.root = Path(memory_dir)
        self.index_path = self.root / "INDEX.md"

    def ensure_tree(self) -> None:
        """Create the directory structure: root + category dirs + empty INDEX.md."""
        self.root.mkdir(parents=True, exist_ok=True)
        for cat in VALID_CATEGORIES:
            (self.root / cat).mkdir(exist_ok=True)
        if not self.index_path.exists():
            self._rebuild_root_index()

    # ── L2 leaf operations ───────────────────────────────────────────────────

    def save(self, name: str, category: str, content: str) -> str:
        """Write a leaf .md file, update _SUMMARY.md and INDEX.md."""
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Must be one of: {VALID_CATEGORIES}"
            )

        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        safe_name = re.sub(r"[^\w\-]", "_", name)[:40]
        filename = f"{ts}_{suffix}_{safe_name}.md"

        cat_dir = self.root / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        leaf_path = cat_dir / filename

        frontmatter = (
            f"---\n"
            f"name: {name}\n"
            f"type: {category}\n"
            f"created: {ts}\n"
            f"---\n\n"
        )
        leaf_path.write_text(frontmatter + content, encoding="utf-8")

        self._rebuild_category_summary(category)
        self._rebuild_root_index()
        return filename

    def delete(self, category: str, filename: str) -> bool:
        """Remove a leaf file and update summary/index."""
        leaf_path = self.root / category / filename
        if not leaf_path.exists():
            return False
        leaf_path.unlink()
        self._rebuild_category_summary(category)
        self._rebuild_root_index()
        return True

    def read_leaf(self, category: str, filename: str) -> str:
        """Read full content of a leaf file."""
        leaf_path = self.root / category / filename
        return leaf_path.read_text(encoding="utf-8")

    # ── L1 category summary operations ───────────────────────────────────────

    def list_category(self, category: str) -> list[dict]:
        """List all memories in a category."""
        cat_dir = self.root / category
        if not cat_dir.is_dir():
            return []
        results = []
        for md_file in sorted(cat_dir.glob("*.md")):
            if md_file.name.startswith("_"):
                continue
            try:
                raw = md_file.read_text(encoding="utf-8")
                name, mem_type = _parse_frontmatter_meta(raw)
                results.append({"name": name, "type": mem_type, "filename": md_file.name})
            except (OSError, ValueError) as exc:
                logger.warning(
                    "skipped %s: %s: %s", md_file.name, type(exc).__name__, exc
                )
        return results

    def get_category_summary(self, category: str) -> str:
        summary_path = self.root / category / "_SUMMARY.md"
        if summary_path.exists():
            return summary_path.read_text(encoding="utf-8")
        return ""

    def _rebuild_category_summary(self, category: str) -> None:
        entries = self.list_category(category)
        lines = [f"# {category} ({len(entries)} entries)\n"]
        for entry in entries:
            lines.append(f"- [{entry['name']}]({entry['filename']})")
        summary_path = self.root / category / "_SUMMARY.md"
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── L0 root index operations ─────────────────────────────────────────────

    def list_all(self) -> list[dict]:
        results = []
        for cat in VALID_CATEGORIES:
            results.extend(self.list_category(cat))
        return results

    def get_root_index(self) -> str:
        if self.index_path.exists():
            content = self.index_path.read_text(encoding="utf-8")
            return self._enforce_caps(content)
        return "# Memory Index (empty)\n"

    def _rebuild_root_index(self) -> None:
        lines = ["# Memory Index"]
        total = 0
        for cat in VALID_CATEGORIES:
            entries = self.list_category(cat)
            count = len(entries)
            total += count
            if count == 0:
                continue
            names_preview = ", ".join(e["name"] for e in entries[:5])
            if count > 5:
                names_preview += f" (+{count - 5} more)"
            lines.append(f"- {cat} ({count}): {names_preview}")

        if total == 0:
            lines.append("(no memories yet)")

        content = "\n".join(lines) + "\n"
        content = self._enforce_caps(content)
        self.index_path.write_text(content, encoding="utf-8")

    @staticmethod
    def _enforce_caps(content: str) -> str:
        content_lines = content.strip().splitlines()
        if len(content_lines) > MAX_INDEX_LINES:
            content_lines = content_lines[:MAX_INDEX_LINES]
            content_lines.append("(truncated — too many entries)")
        result = "\n".join(content_lines) + "\n"
        if len(result.encode("utf-8")) > MAX_INDEX_BYTES:
            while len(result.encode("utf-8")) > MAX_INDEX_BYTES and content_lines:
                content_lines.pop()
                result = "\n".join(content_lines) + "\n(truncated — size limit)\n"
        return result


# Wrap the constructor so callers can use the canonical kwarg name.
def _btree_factory(memory_dir: Path | str) -> BTreeMemoryStore:
    return BTreeMemoryStore(memory_dir)


register_memory_backend("btree", _btree_factory)
