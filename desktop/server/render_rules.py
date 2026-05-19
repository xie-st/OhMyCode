"""Shared truncation rules for desktop event rendering.

These mirror the magic numbers in ``ohmycode/_cli/output.py:287-313`` so the
CLI and the desktop UI present the same preview shape. Keeping the rules in
``desktop/`` for now (rather than ``ohmycode/core/``) avoids touching the
kernel. If a third frontend ever needs the same logic, lift this module to
``ohmycode/core/render_rules.py``.

The companion test ``tests/desktop/test_render_rules_align_cli.py`` asserts
the constants below stay in sync with the CLI source.
"""

from __future__ import annotations

import json
from typing import Any

RESULT_MAX_LINES = 10
RESULT_MAX_CHARS = 500
PARAMS_MAX_CHARS = 100


def truncate_params(params: Any) -> str:
    """Return a short JSON preview of tool params (matches CLI behaviour)."""
    text = json.dumps(params, ensure_ascii=False, default=str)
    if len(text) <= PARAMS_MAX_CHARS:
        return text
    return text[: PARAMS_MAX_CHARS - 3] + "..."


def truncate_result(text: str) -> tuple[str, bool]:
    """Return ``(preview, is_truncated)`` matching the CLI's 10-line / 500-char rule."""
    if text is None:
        return ("", False)
    lines = text.splitlines()
    if len(lines) > RESULT_MAX_LINES:
        head = "\n".join(lines[:RESULT_MAX_LINES])
        return (f"{head}\n… ({len(lines)} lines total)", True)
    if len(text) > RESULT_MAX_CHARS:
        return (text[: RESULT_MAX_CHARS - 3] + "...", True)
    return (text, False)
