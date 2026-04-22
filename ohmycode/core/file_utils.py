"""Shared file reading utility for tools and message pre-processing."""

from __future__ import annotations

from pathlib import Path


def read_lines_numbered(
    path: Path,
    offset: int = 1,
    limit: int | None = None,
    max_bytes: int | None = None,
    max_lines: int | None = None,
) -> tuple[str, bool]:
    """Read a file and return (numbered_text, is_truncated).

    offset: 1-indexed first line to include.
    limit:  max lines to return (None = all).
    max_bytes: hard byte cap applied before decoding (None = no cap).
    max_lines: hard line cap applied after splitting (None = no cap).

    Raises OSError / FileNotFoundError / PermissionError on I/O failure.
    """
    raw = path.read_bytes()

    truncated = False
    if max_bytes is not None and len(raw) > max_bytes:
        raw = raw[:max_bytes]
        truncated = True

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)

    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    start = offset - 1
    end = (start + limit) if limit is not None else len(lines)
    selected = lines[start:end]

    numbered = "".join(f"{start + i + 1}\t{line}" for i, line in enumerate(selected))
    return numbered, truncated
