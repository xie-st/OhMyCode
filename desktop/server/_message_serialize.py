"""Serialize kernel Message dataclasses for desktop persistence.

The desktop store keeps the same message hierarchy that providers consume.
That preserves assistant tool calls and their matching tool result messages
across reloads instead of flattening history into UI-only text rows.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

from ohmycode.core.messages import (
    AssistantMessage,
    ImageBlock,
    Message,
    SystemMessage,
    ToolResultMessage,
    ToolUseBlock,
    UserMessage,
)


_MESSAGE_TYPES = {
    cls.__name__: cls
    for cls in (
        UserMessage,
        AssistantMessage,
        ToolResultMessage,
        SystemMessage,
    )
}


def serialize_message(message: Message) -> dict:
    """Serialize a kernel message as {"type": <ClassName>, "data": {...}}."""
    message_type = type(message).__name__
    if message_type not in _MESSAGE_TYPES or not is_dataclass(message):
        raise TypeError(f"Unsupported message: {type(message).__name__}")
    return {"type": message_type, "data": asdict(message)}


def deserialize_message(data: dict) -> Message:
    """Deserialize a persisted kernel message."""
    message_type = data["type"]
    fields = dict(data["data"])
    message_class = _MESSAGE_TYPES[message_type]
    fields.pop("role", None)

    if message_class is UserMessage:
        fields["content"] = _deserialize_user_content(fields.get("content"))
    elif message_class is AssistantMessage:
        fields["tool_calls"] = [
            _deserialize_tool_use(item)
            for item in fields.get("tool_calls", [])
            if isinstance(item, dict)
        ]

    return message_class(**fields)


def _deserialize_user_content(content: object) -> object:
    if not isinstance(content, list):
        return content
    restored = []
    for item in content:
        if isinstance(item, dict) and {"media_type", "data"} <= set(item):
            restored.append(ImageBlock(media_type=item["media_type"], data=item["data"]))
        else:
            restored.append(item)
    return restored


def _deserialize_tool_use(data: dict) -> ToolUseBlock:
    return ToolUseBlock(
        tool_use_id=data["tool_use_id"],
        tool_name=data["tool_name"],
        params=data.get("params", {}),
    )
