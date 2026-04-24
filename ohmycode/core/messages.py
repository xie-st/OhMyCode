"""Conversation message types and streaming event definitions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Union


# --- Conversation messages ---


@dataclass
class ToolUseBlock:
    """One tool call inside an assistant message."""

    tool_use_id: str
    tool_name: str
    params: dict


@dataclass
class ImageBlock:
    """A base64-encoded image to embed in a user message."""

    media_type: str  # e.g. "image/png"
    data: str        # base64-encoded bytes


# Content item in a multimodal user message
UserContent = Union[str, ImageBlock]


@dataclass
class UserMessage:
    # Plain string for text-only; list when images are present.
    content: Union[str, list[UserContent]]
    role: str = field(default="user", init=False)

    def to_api_dict(self) -> dict:
        if isinstance(self.content, str):
            return {"role": self.role, "content": self.content}
        # Multimodal: build OpenAI-style content list
        parts: list[dict] = []
        for item in self.content:
            if isinstance(item, str):
                if item:
                    parts.append({"type": "text", "text": item})
            else:
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{item.media_type};base64,{item.data}"},
                })
        return {"role": self.role, "content": parts}


@dataclass
class AssistantMessage:
    content: str
    tool_calls: list[ToolUseBlock] = field(default_factory=list)
    role: str = field(default="assistant", init=False)

    def to_api_dict(self) -> dict:
        d: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.tool_use_id,
                    "type": "function",
                    "function": {
                        "name": tc.tool_name,
                        "arguments": json.dumps(tc.params),
                    },
                }
                for tc in self.tool_calls
            ]
        return d


@dataclass
class ToolResultMessage:
    """Tool execution result sent back to the model."""

    tool_use_id: str
    content: str
    is_error: bool = False
    role: str = field(default="tool", init=False)

    def to_api_dict(self) -> dict:
        return {
            "role": self.role,
            "tool_call_id": self.tool_use_id,
            "content": self.content,
        }


@dataclass
class SystemMessage:
    content: str
    role: str = field(default="system", init=False)

    def to_api_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


# Union of message types in conversation history
Message = Union[UserMessage, AssistantMessage, ToolResultMessage, SystemMessage]


# --- Streaming events (yielded by the conversation loop to the CLI) ---


@dataclass
class TextChunk:
    """A text fragment from model streaming output."""

    text: str


@dataclass
class ThinkingChunk:
    """A fragment of extended thinking content from the model."""

    text: str


@dataclass
class ToolCallStreaming:
    """A tool call has started streaming; name is known but params not yet complete."""

    tool_name: str
    tool_use_id: str


@dataclass
class ToolCallStart:
    """Notification: a tool call was parsed from the stream."""

    tool_name: str
    tool_use_id: str
    params: dict


@dataclass
class ToolCallResult:
    """Result of a tool execution."""

    tool_use_id: str
    result: str
    is_error: bool


@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class TurnComplete:
    """Signals that a turn in the conversation loop has finished."""

    finish_reason: str  # "stop" | "tool_use" | "cancelled" | "max_turns"
    usage: TokenUsage


# Union of all events the loop may yield
StreamEvent = Union[TextChunk, ThinkingChunk, ToolCallStreaming, ToolCallStart, ToolCallResult, TurnComplete]
