"""Tests for ConversationLoop core path."""

from __future__ import annotations

import pytest

from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.loop import ConversationLoop
from ohmycode.core.messages import TextChunk, TurnComplete
from ohmycode.providers.base import register_provider


@pytest.mark.asyncio
async def test_simple_conversation(mock_provider):
    register_provider("mock", lambda **kw: mock_provider)
    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = ConversationLoop(config=config)
    conv._provider = mock_provider
    conv._system_prompt = "You are helpful."
    conv.add_user_message("Hello")
    events = []
    async for event in conv.run_turn():
        events.append(event)
    text_events = [e for e in events if isinstance(e, TextChunk)]
    assert len(text_events) >= 1
    assert text_events[0].text == "Hello from mock!"


@pytest.mark.asyncio
async def test_turn_complete_emitted(mock_provider):
    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = ConversationLoop(config=config)
    conv._provider = mock_provider
    conv._system_prompt = "You are helpful."
    conv.add_user_message("Hi")
    events = []
    async for event in conv.run_turn():
        events.append(event)
    turn_complete_events = [e for e in events if isinstance(e, TurnComplete)]
    assert len(turn_complete_events) >= 1
    assert turn_complete_events[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_error_handling(mock_provider):
    """Provider that raises an exception should yield an API Error TextChunk."""

    class ErrorProvider:
        name = "error"

        async def stream(self, messages, tools, system, model, **kwargs):
            raise RuntimeError("simulated API failure")
            yield  # make it an async generator

    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")
    conv = ConversationLoop(config=config)
    conv._provider = ErrorProvider()
    conv._system_prompt = "You are helpful."
    conv.add_user_message("Hi")
    events = []
    async for event in conv.run_turn():
        events.append(event)

    text_events = [e for e in events if isinstance(e, TextChunk)]
    assert any("API Error" in e.text for e in text_events)

    turn_complete_events = [e for e in events if isinstance(e, TurnComplete)]
    assert turn_complete_events[-1].finish_reason == "error"


@pytest.mark.asyncio
async def test_multiple_responses(mock_provider):
    """MockProvider cycles through responses correctly."""
    provider = mock_provider.__class__(responses=["First response", "Second response"])
    config = OhMyCodeConfig(provider="mock", model="test", mode="auto", api_key="x")

    conv1 = ConversationLoop(config=config)
    conv1._provider = provider
    conv1._system_prompt = "sys"
    conv1.add_user_message("Turn 1")
    events1 = [e async for e in conv1.run_turn()]
    texts1 = [e.text for e in events1 if isinstance(e, TextChunk)]
    assert texts1[0] == "First response"

    conv2 = ConversationLoop(config=config)
    conv2._provider = provider
    conv2._system_prompt = "sys"
    conv2.add_user_message("Turn 2")
    events2 = [e async for e in conv2.run_turn()]
    texts2 = [e.text for e in events2 if isinstance(e, TextChunk)]
    assert texts2[0] == "Second response"
