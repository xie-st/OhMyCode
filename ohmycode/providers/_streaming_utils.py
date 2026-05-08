"""Caller-side helpers for collecting provider streams into strings.

These are utilities for users *of* a provider — they do not belong on the
``Provider`` interface itself.
"""

from __future__ import annotations

from typing import Any

from ohmycode.core.messages import TextChunk


async def stream_to_text(
    provider: Any, messages: list, model: str, system: str = ""
) -> str:
    """Collect every TextChunk from provider.stream() into a single string."""
    collected = ""
    async for event in provider.stream(
        messages=messages, tools=[], system=system, model=model
    ):
        if isinstance(event, TextChunk):
            collected += event.text
    return collected


async def stream_to_box(
    provider: Any, messages: list, model: str, system: str = "", box: Any = None
) -> str:
    """Like ``stream_to_text`` but also pushes each chunk to ``box.push()``."""
    collected = ""
    async for event in provider.stream(
        messages=messages, tools=[], system=system, model=model
    ):
        if isinstance(event, TextChunk):
            collected += event.text
            if box is not None:
                box.push(event.text)
    return collected
