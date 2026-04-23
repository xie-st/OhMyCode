"""Tests for the OpenAI-compatible provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ohmycode.providers.base import PROVIDER_REGISTRY


def test_openai_provider_is_registered():
    import ohmycode.providers.openai  # noqa: F401
    assert "openai" in PROVIDER_REGISTRY


def test_openai_provider_instantiation():
    from ohmycode.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        api_key="test-key",
        base_url="http://localhost:8080/v1",
    )
    assert provider.name == "openai"


def _make_stream_chunk(content=None, finish_reason=None, tool_calls=None):
    """Build a minimal mock chunk matching the OpenAI streaming response shape."""
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = None
    return chunk


@pytest.mark.asyncio
async def test_stream_passes_reasoning_effort():
    """reasoning_effort kwarg is forwarded to the OpenAI API call."""
    from ohmycode.providers.openai import OpenAIProvider
    from ohmycode.core.messages import UserMessage

    provider = OpenAIProvider(api_key="test-key")

    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)

        async def _gen():
            yield _make_stream_chunk(content="hi", finish_reason="stop")

        return _gen()

    provider.client.chat.completions.create = fake_create

    messages = [UserMessage(content="hello")]
    events = []
    async for event in provider.stream(
        messages=messages,
        tools=[],
        system="sys",
        model="o4-mini",
        reasoning_effort="high",
    ):
        events.append(event)

    assert captured.get("reasoning_effort") == "high"


@pytest.mark.asyncio
async def test_stream_no_reasoning_effort_by_default():
    """reasoning_effort is NOT included in the API call when not passed."""
    from ohmycode.providers.openai import OpenAIProvider
    from ohmycode.core.messages import UserMessage

    provider = OpenAIProvider(api_key="test-key")

    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)

        async def _gen():
            yield _make_stream_chunk(content="hi", finish_reason="stop")

        return _gen()

    provider.client.chat.completions.create = fake_create

    messages = [UserMessage(content="hello")]
    async for _ in provider.stream(
        messages=messages,
        tools=[],
        system="sys",
        model="gpt-4o",
    ):
        pass

    assert "reasoning_effort" not in captured
