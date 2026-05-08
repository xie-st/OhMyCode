"""OpenAI-compatible provider (OpenAI, Azure OpenAI, Ollama, etc.)."""

from __future__ import annotations

from typing import Any, AsyncIterator

from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai import APIStatusError, RateLimitError

from ohmycode.core.messages import (
    Message,
    StreamEvent,
    TextChunk,
    ToolCallStart,
    ToolCallStreaming,
    TurnComplete,
)
from ohmycode.providers.base import BaseProvider, ToolDef, register_provider


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        azure_endpoint: str = "",
        azure_api_version: str = "2024-02-01",
        **kwargs: Any,
    ):
        if azure_endpoint:
            self.client = AsyncAzureOpenAI(
                api_key=api_key,
                api_version=azure_api_version,
                azure_endpoint=azure_endpoint,
            )
        else:
            client_kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            self.client = AsyncOpenAI(**client_kwargs)

    def _is_retryable(self, exc: BaseException) -> bool:
        if isinstance(exc, RateLimitError):
            return True
        if isinstance(exc, APIStatusError) and exc.status_code == 503:
            return True
        return False

    def _build_request_kwargs(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        system: str,
        model: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        api_messages = [{"role": "system", "content": system}]
        for msg in messages:
            api_messages.append(msg.to_api_dict())

        request_kwargs: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "stream": True,
        }
        if tools:
            request_kwargs["tools"] = [t.to_api_dict() for t in tools]
        if "reasoning_effort" in kwargs:
            request_kwargs["reasoning_effort"] = kwargs["reasoning_effort"]
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
        response = await self._with_retry(
            lambda: self.client.chat.completions.create(**request_kwargs)
        )

        tool_calls_acc: dict[int, dict] = {}
        finish_reason = "stop"
        prompt_tokens = 0
        completion_tokens = 0

        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            if chunk.choices[0].finish_reason:
                fr = chunk.choices[0].finish_reason
                finish_reason = "tool_use" if fr == "tool_calls" else fr

            if delta.content:
                yield TextChunk(text=delta.content)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc_delta.id or "",
                            "name": tc_delta.function.name or "" if tc_delta.function else "",
                            "arguments": "",
                        }
                        name = tool_calls_acc[idx]["name"]
                        uid = tool_calls_acc[idx]["id"]
                        if name:
                            yield ToolCallStreaming(tool_name=name, tool_use_id=uid)
                    if tc_delta.id:
                        tool_calls_acc[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_acc[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

            if chunk.usage:
                prompt_tokens = chunk.usage.prompt_tokens or 0
                completion_tokens = chunk.usage.completion_tokens or 0

        for ev in self._emit_tool_calls(tool_calls_acc):
            yield ev
        yield self._make_turn_complete(finish_reason, prompt_tokens, completion_tokens)


register_provider("openai", OpenAIProvider)
