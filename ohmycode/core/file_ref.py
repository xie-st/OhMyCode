"""@ file reference: path completion helpers and message expansion."""

from __future__ import annotations

import re
from pathlib import Path

from ohmycode.core.file_utils import read_lines_numbered

MAX_FILE_BYTES = 100_000  # 100 KB per file
MAX_FILE_LINES = 2_000

_AT_REF_RE = re.compile(r"@((?:[^\s@\"']+))")


def get_at_completions(prefix: str, cwd: str) -> list[tuple[str, str]]:
    """Return (path_string, meta_label) pairs for Tab completion after @.

    prefix: text typed after @, e.g. "" or "src/" or "src/mai"
    cwd:    current working directory
    """
    base = Path(cwd)
    try:
        if "/" in prefix or "\\" in prefix:
            parent_str, _, _ = prefix.rpartition("/")
            parent = (base / parent_str) if parent_str else base
            if not parent.is_dir():
                return []
            candidates = list(parent.iterdir())
        else:
            candidates = list(base.iterdir())
    except PermissionError:
        return []

    name_filter = prefix.split("/")[-1].lower()
    results: list[tuple[str, str]] = []

    for entry in sorted(candidates, key=lambda p: (p.is_file(), p.name)):
        if not entry.name.lower().startswith(name_filter):
            continue
        if entry.name.startswith("."):
            continue
        try:
            rel_str = str(entry.relative_to(base)).replace("\\", "/")
        except ValueError:
            continue
        if entry.is_dir():
            results.append((rel_str + "/", "dir"))
        else:
            try:
                size_kb = f"{entry.stat().st_size // 1024}KB"
            except OSError:
                size_kb = ""
            results.append((rel_str, size_kb))

    return results[:50]


def _read_file_content(file_path: Path) -> tuple[str, bool]:
    """Read and format one file for injection. Returns (block, is_error)."""
    try:
        numbered, truncated = read_lines_numbered(
            file_path, max_bytes=MAX_FILE_BYTES, max_lines=MAX_FILE_LINES
        )
    except FileNotFoundError:
        return f"[Error: file not found: {file_path}]", True
    except PermissionError:
        return f"[Error: permission denied: {file_path}]", True
    except OSError as exc:
        return f"[Error reading {file_path}: {exc}]", True

    if truncated:
        numbered += f"\n[... truncated at {MAX_FILE_LINES} lines / {MAX_FILE_BYTES // 1024}KB ...]"

    return numbered, False


def expand_file_refs(text: str, cwd: str) -> tuple[str, list[str]]:
    """Replace all @path tokens in text with file contents.

    Returns (expanded_text, warnings). On error, leaves @path unchanged
    and appends a warning. Never raises.
    """
    warnings: list[str] = []
    base = Path(cwd)

    def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
        raw_path = match.group(1)
        candidate = (base / raw_path).resolve()
        block, is_error = _read_file_content(candidate)
        if is_error:
            warnings.append(block)
            return match.group(0)  # keep original @path on error
        header = f'\n<file path="{raw_path}">\n'
        footer = "\n</file>\n"
        return header + block + footer

    expanded = _AT_REF_RE.sub(_replace, text)
    return expanded, warnings
