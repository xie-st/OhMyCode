from dataclasses import asdict, is_dataclass

from desktop.server.render_rules import truncate_params, truncate_result
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
    """Serialize a stream event as {"type": <ClassName>, "data": {...}}.

    For ToolCallStart / ToolCallResult we also embed short ``*_preview``
    fields produced by ``render_rules`` so the frontend can render the
    same shape the CLI shows (10 lines / 500 chars / 100-char params)
    without re-implementing the truncation logic.
    """
    event_type = type(event).__name__
    if event_type not in _EVENT_TYPES or not is_dataclass(event):
        raise TypeError(f"Unsupported stream event: {type(event).__name__}")
    data = asdict(event)
    if isinstance(event, ToolCallStart):
        data["params_preview"] = truncate_params(event.params)
    elif isinstance(event, ToolCallResult):
        preview, is_truncated = truncate_result(event.result)
        data["result_preview"] = preview
        data["is_truncated"] = is_truncated
    return {"type": event_type, "data": data}


_PREVIEW_FIELDS = {"params_preview", "result_preview", "is_truncated"}


def deserialize_event(data: dict) -> StreamEvent:
    """Deserialize a stream event, including nested TokenUsage data.

    Strips ``*_preview`` / ``is_truncated`` fields injected by
    ``serialize_event`` since they are not part of the kernel dataclasses.
    """
    event_type = data["type"]
    fields = {k: v for k, v in data["data"].items() if k not in _PREVIEW_FIELDS}
    event_class = _EVENT_TYPES[event_type]

    if event_class is TurnComplete and isinstance(fields.get("usage"), dict):
        fields["usage"] = TokenUsage(**fields["usage"])

    return event_class(**fields)
