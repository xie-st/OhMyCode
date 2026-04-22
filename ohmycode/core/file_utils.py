"""Shared file reading utility for tools and message pre-processing."""

from __future__ import annotations

import base64
from pathlib import Path

IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})
IMAGE_MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def read_image_b64(path: Path) -> tuple[str, str]:
    """Read an image file and return (base64_data, media_type).

    Raises ValueError if the file exceeds MAX_IMAGE_BYTES.
    Raises OSError / FileNotFoundError on I/O failure.
    """
    raw = path.read_bytes()
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image too large: {len(raw) // 1024}KB > {MAX_IMAGE_BYTES // 1024}KB limit"
        )
    media_type = IMAGE_MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg")
    return base64.standard_b64encode(raw).decode("ascii"), media_type


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
