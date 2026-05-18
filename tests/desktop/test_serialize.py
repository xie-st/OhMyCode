import pytest

from ohmycode.core.messages import (
    SubAgentDone,
    SubAgentToolUse,
    TextChunk,
    ThinkingChunk,
    TokenUsage,
    ToolCallResult,
    ToolCallStart,
    ToolCallStreaming,
    TurnComplete,
)

from desktop.server._serialize import deserialize_event, serialize_event


@pytest.mark.parametrize(
    "event",
    [
        TextChunk(text="hello"),
        ThinkingChunk(text="thinking"),
        ToolCallStreaming(tool_name="Read", tool_use_id="tool-1"),
        ToolCallStart(tool_name="Write", tool_use_id="tool-2", params={"path": "x"}),
        ToolCallResult(tool_use_id="tool-3", result="ok", is_error=False),
        TurnComplete(
            finish_reason="stop",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        ),
        SubAgentToolUse(tool_name="agent"),
        SubAgentDone(is_error=False),
    ],
)
def test_stream_events_round_trip(event):
    payload = serialize_event(event)

    assert payload["type"] == type(event).__name__
    assert deserialize_event(payload) == event


def test_turn_complete_restores_token_usage_dataclass():
    event = TurnComplete(
        finish_reason="stop",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )

    restored = deserialize_event(serialize_event(event))

    assert isinstance(restored.usage, TokenUsage)
    assert restored.usage.prompt_tokens == 10
    assert restored.usage.completion_tokens == 20
    assert restored.usage.total_tokens == 30


def test_serialize_event_rejects_unknown_objects():
    with pytest.raises(TypeError):
        serialize_event(123)


def test_deserialize_event_rejects_unknown_type():
    with pytest.raises((KeyError, ValueError)):
        deserialize_event({"type": "FakeEvent", "data": {}})
