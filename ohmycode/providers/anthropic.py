"""Anthropic Claude provider with streaming and tool calling."""

from __future__ import annotations

from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic
from anthropic import APIStatusError, RateLimitError

from ohmycode.core.messages import (
    AssistantMessage,
    ImageBlock,
    Message,
    StreamEvent,
    TextChunk,
    ThinkingChunk,
    ToolCallStart,
    ToolCallStreaming,
    ToolResultMessage,
    TurnComplete,
    UserMessage,
)
from ohmycode.providers.base import BaseProvider, ToolDef, register_provider


# Claude 4 generation supports adaptive thinking; older models use manual budgets.
_ADAPTIVE_THINKING_MODELS = ("claude-opus-4", "claude-sonnet-4", "claude-haiku-4")
_LEGACY_THINKING_BUDGETS = {"low": 1024, "medium": 8000, "high": 32000}
_THINKING_MIN_MAX_TOKENS = 16000


def _resolve_thinking_kwargs(model: str, effort: str, current_max_tokens: int) -> dict:
    """Build the request kwargs needed to enable extended thinking for `model`."""
    out: dict = {}
    if any(m in model for m in _ADAPTIVE_THINKING_MODELS):
        out["thinking"] = {"type": "adaptive", "effort": effort}
    else:
        budget = _LEGACY_THINKING_BUDGETS.get(effort, _LEGACY_THINKING_BUDGETS["medium"])
        out["thinking"] = {"type": "enabled", "budget_tokens": budget}
    if current_max_tokens < _THINKING_MIN_MAX_TOKENS:
        out["max_tokens"] = _THINKING_MIN_MAX_TOKENS
    return out


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, api_key: str = "", base_url: str = "", auth_token: str = "", **kwargs: Any):
        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url
        if auth_token:
            client_kwargs["auth_token"] = auth_token
        self.client = AsyncAnthropic(**client_kwargs)

    def _is_retryable(self, exc: BaseException) -> bool:
        if isinstance(exc, RateLimitError):
            return True
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            return status == 503 or status == 529
        return False

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal message format to Anthropic API format."""
        result: list[dict] = []
        for msg in messages:
            if isinstance(msg, UserMessage):
                if isinstance(msg.content, str):
                    result.append({"role": "user", "content": msg.content})
                else:
                    content_blocks: list[dict] = []
                    for item in msg.content:
                        if isinstance(item, str):
                            if item:
                                content_blocks.append({"type": "text", "text": item})
                        elif isinstance(item, ImageBlock):
                            content_blocks.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": item.media_type,
                                    "data": item.data,
                                },
                            })
                    result.append({"role": "user", "content": content_blocks})

            elif isinstance(msg, AssistantMessage):
                content: list[dict] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc.tool_use_id,
                            "name": tc.tool_name,
                            "input": tc.params,
                        }
                    )
                result.append({"role": "assistant", "content": content if content else ""})

            elif isinstance(msg, ToolResultMessage):
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_use_id,
                    "content": msg.content,
                }
                if msg.is_error:
                    tool_result_block["is_error"] = True

                if result and result[-1]["role"] == "user" and isinstance(result[-1]["content"], list):
                    result[-1]["content"].append(tool_result_block)
                else:
                    result.append({"role": "user", "content": [tool_result_block]})

        return result

    def _build_request_kwargs(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        system: str,
        model: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        request_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": self._convert_messages(messages),
            "system": system,
        }
        if tools:
            request_kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]
        if "reasoning_effort" in kwargs:
            request_kwargs.update(
                _resolve_thinking_kwargs(
                    model=model,
                    effort=kwargs["reasoning_effort"],
                    current_max_tokens=request_kwargs.get("max_tokens", 0),
                )
            )
        return request_kwargs

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        system: str,
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        request_kwargs = self._build_request_kwargs(
            messages, tools, system, model, **kwargs
        )

        finish_reason = "stop"
        prompt_tokens = 0
        completion_tokens = 0
        tool_calls_acc: dict[int, dict] = {}

        # The Anthropic SDK exposes streaming as an async context manager. The
        # retry has to wrap the *entry* into the stream, not the iteration.
        stream_cm = await self._with_retry(
            lambda: self._open_stream(request_kwargs)
        )

        async with stream_cm as stream:
            async for event in stream:
                event_type = event.type

                if event_type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        idx = event.index
                        tool_calls_acc[idx] = {
                            "id": block.id,
                            "name": block.name,
                            "arguments": "",
                        }
                        yield ToolCallStreaming(tool_name=block.name, tool_use_id=block.id)

                elif event_type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield TextChunk(text=delta.text)
                    elif delta.type == "thinking_delta":
                        yield ThinkingChunk(text=delta.thinking)
                    elif delta.type == "input_json_delta":
                        idx = event.index
                        if idx in tool_calls_acc:
                            tool_calls_acc[idx]["arguments"] += delta.partial_json

                elif event_type == "message_delta":
                    if hasattr(event, "delta"):
                        stop_reason = getattr(event.delta, "stop_reason", None)
                        if stop_reason == "tool_use":
                            finish_reason = "tool_use"
                        elif stop_reason:
                            finish_reason = stop_reason
                    if hasattr(event, "usage"):
                        completion_tokens = getattr(event.usage, "output_tokens", 0)

                elif event_type == "message_start":
                    if hasattr(event, "message") and hasattr(event.message, "usage"):
                        prompt_tokens = getattr(event.message.usage, "input_tokens", 0)
                        completion_tokens = getattr(event.message.usage, "output_tokens", 0)

        for ev in self._emit_tool_calls(tool_calls_acc):
            yield ev
        yield self._make_turn_complete(finish_reason, prompt_tokens, completion_tokens)

    async def _open_stream(self, request_kwargs: dict[str, Any]) -> Any:
        """Return the streaming async-context-manager from the SDK.

        Wrapped in an async function so ``_with_retry`` can call it via a
        zero-arg lambda factory.
        """
        return self.client.messages.stream(**request_kwargs)


register_provider("anthropic", AnthropicProvider)
