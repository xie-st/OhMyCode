"""In-process event bus for ``StreamEvent`` fan-out.

The bus does the bare minimum a 3K-LOC agent kernel needs:

- ``subscribe(handler)`` — register a sync or async callable
- ``publish(event)``     — deliver in subscription order, sync handlers run first
- ``buffer(callback)``   — every published event also goes through ``callback``,
                           used by the loop to interleave sub-agent events
                           with ``ToolCallResult`` in the iterator stream

Deliberately not pub/sub: no topics, no priorities, no backpressure, no
dead-letter queue. Adding any of those is a feature request, not a bug fix.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from ohmycode.core.messages import StreamEvent


Handler = Callable[[StreamEvent], "Any | Awaitable[Any]"]


class EventBus:
    """Minimal in-process event bus."""

    def __init__(self) -> None:
        self._handlers: list[Handler] = []
        self._buffer_sink: Callable[[StreamEvent], None] | None = None

    def subscribe(self, handler: Handler) -> Callable[[], None]:
        """Register ``handler``; returns an unsubscribe function."""
        self._handlers.append(handler)

        def _unsubscribe() -> None:
            try:
                self._handlers.remove(handler)
            except ValueError:
                pass

        return _unsubscribe

    def set_buffer(self, sink: Callable[[StreamEvent], None] | None) -> None:
        """Install a buffer that receives every event before subscribers."""
        self._buffer_sink = sink

    async def publish(self, event: StreamEvent) -> None:
        """Deliver ``event`` to the buffer (if any), then every subscriber.

        Sync handlers run inline; async handlers are awaited in registration
        order. A handler that raises is logged-and-swallowed so one bad
        subscriber cannot wedge the kernel.
        """
        if self._buffer_sink is not None:
            try:
                self._buffer_sink(event)
            except Exception:
                pass

        for handler in list(self._handlers):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass
