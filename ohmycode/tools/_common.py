"""Shared helpers for built-in tools."""

from __future__ import annotations

import html
import re
from pathlib import Path

MAX_RESULTS = 200


def format_file_error(path: Path | str, exc: BaseException) -> str:
    """Render a file-access error as a tool-friendly string."""
    if isinstance(exc, FileNotFoundError):
        return f"File not found: {path}"
    if isinstance(exc, PermissionError):
        return f"Permission denied: {path}"
    if isinstance(exc, IsADirectoryError):
        return f"Path is a directory: {path}"
    return f"Error accessing {path}: {exc}"


_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    """Remove script/style blocks, HTML tags, decode entities, collapse whitespace."""
    text = _SCRIPT_RE.sub("", text)
    text = _STYLE_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()
