from dataclasses import asdict, is_dataclass

from ohmycode.core.messages import (
    StreamEvent,
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


_EVENT_TYPES = {
    cls.__name__: cls
    for cls in (
        TextChunk,
        ThinkingChunk,
        ToolCallStreaming,
        ToolCallStart,
        ToolCallResult,
        TurnComplete,
        SubAgentToolUse,
        SubAgentDone,
    )
}


def serialize_event(event: StreamEvent) -> dict:
    """Serialize a stream event as {"type": <ClassName>, "data": {...}}."""
    event_type = type(event).__name__
    if event_type not in _EVENT_TYPES or not is_dataclass(event):
        raise TypeError(f"Unsupported stream event: {type(event).__name__}")
    return {"type": event_type, "data": asdict(event)}


def deserialize_event(data: dict) -> StreamEvent:
    """Deserialize a stream event, including nested TokenUsage data."""
    event_type = data["type"]
    fields = dict(data["data"])
    event_class = _EVENT_TYPES[event_type]

    if event_class is TurnComplete and isinstance(fields.get("usage"), dict):
        fields["usage"] = TokenUsage(**fields["usage"])

    return event_class(**fields)
