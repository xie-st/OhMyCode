"""Tests for the in-process EventBus."""

from __future__ import annotations

import pytest

from ohmycode.core.events import EventBus
from ohmycode.core.messages import TextChunk, TurnComplete


@pytest.mark.asyncio
async def test_publish_to_single_sync_handler():
    bus = EventBus()
    seen: list = []
    bus.subscribe(lambda e: seen.append(e))

    await bus.publish(TextChunk(text="hi"))
    assert len(seen) == 1
    assert seen[0].text == "hi"


@pytest.mark.asyncio
async def test_publish_to_multiple_handlers_in_order():
    bus = EventBus()
    seen: list = []
    bus.subscribe(lambda e: seen.append(("a", e.text)))
    bus.subscribe(lambda e: seen.append(("b", e.text)))

    await bus.publish(TextChunk(text="x"))
    assert seen == [("a", "x"), ("b", "x")]


@pytest.mark.asyncio
async def test_async_handler_is_awaited():
    bus = EventBus()
    seen: list = []

    async def _async_handler(e):
        seen.append(e.text)

    bus.subscribe(_async_handler)
    await bus.publish(TextChunk(text="y"))
    assert seen == ["y"]


@pytest.mark.asyncio
async def test_buffer_runs_before_subscribers():
    bus = EventBus()
    order: list[str] = []

    bus.set_buffer(lambda e: order.append("buffer"))
    bus.subscribe(lambda e: order.append("sub"))

    await bus.publish(TextChunk(text="z"))
    assert order == ["buffer", "sub"]


@pytest.mark.asyncio
async def test_subscriber_exception_does_not_block_others():
    bus = EventBus()
    seen: list = []

    def _bad(e):
        raise RuntimeError("boom")

    bus.subscribe(_bad)
    bus.subscribe(lambda e: seen.append(e.text))
    await bus.publish(TextChunk(text="ok"))
    assert seen == ["ok"]


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    seen: list = []
    unsubscribe = bus.subscribe(lambda e: seen.append(e))
    unsubscribe()
    await bus.publish(TurnComplete(finish_reason="stop", usage=None))
    assert seen == []
