"""Async conversation loop with tool execution and permission checks."""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.compression import (
    auto_import_compression_strategies,
    get_compression_strategy,
)
from ohmycode.core.context import ContextManager
from ohmycode.core.messages import (
    AssistantMessage,
    ImageBlock,
    Message,
    StreamEvent,
    TextChunk,
    ThinkingChunk,
    ToolCallResult,
    ToolCallStart,
    ToolCallStreaming,
    ToolResultMessage,
    ToolUseBlock,
    TokenUsage,
    TurnComplete,
    UserMessage,
)
from ohmycode.core.permissions import check_permission
from ohmycode.core.system_prompt import build_system_prompt, find_project_instructions
from ohmycode.providers.base import auto_import_providers, get_provider
from ohmycode.tools.base import ToolContext, auto_import_tools, get_tool_defs, run_tool_calls


@dataclass
class _RoundState:
    """Mutable container for what one streaming round produced."""

    collected_text: str = ""
    collected_tool_calls: list[ToolCallStart] = field(default_factory=list)
    last_usage: TokenUsage = field(
        default_factory=lambda: TokenUsage(0, 0, 0)
    )
    last_finish_reason: str = "stop"


class ConversationLoop:
    """Core loop driving multi-turn conversation (including tool calls)."""

    def __init__(
        self,
        config: OhMyCodeConfig,
        confirm_fn: Callable[[str, dict], Awaitable[str]] | None = None,
    ) -> None:
        self.config = config
        self.confirm_fn = confirm_fn
        self.messages: list[Message] = []
        self.auto_approved: dict[str, bool] = {}
        self._cancelled: bool = False
        self._provider: Any = None
        self._system_prompt: str = ""
        self.think: str | None = None
        auto_import_compression_strategies()
        self._compression: Any = get_compression_strategy(
            config.compression_strategy,
            token_budget=config.token_budget,
            output_reserved=config.output_tokens_reserved,
        )
        # The default tiered strategy *is* a ``ContextManager``, so it doubles
        # as the token-counting helper used by ``get_status_snapshot``.
        # When a custom strategy is plugged in that is *not* a ``ContextManager``,
        # we keep a separate one for measurement.
        self.context_mgr = (
            self._compression
            if isinstance(self._compression, ContextManager)
            else ContextManager(
                token_budget=config.token_budget,
                output_reserved=config.output_tokens_reserved,
            )
        )

    # ── Setup ────────────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Initialize: import providers/tools, create provider, build system prompt."""
        auto_import_providers()
        auto_import_tools()

        provider_kwargs: dict[str, Any] = {}
        if self.config.api_key:
            provider_kwargs["api_key"] = self.config.api_key
        if self.config.base_url:
            provider_kwargs["base_url"] = self.config.base_url
        if self.config.auth_token:
            provider_kwargs["auth_token"] = self.config.auth_token
        if self.config.azure_endpoint:
            provider_kwargs["azure_endpoint"] = self.config.azure_endpoint
            provider_kwargs["azure_api_version"] = self.config.azure_api_version

        self._provider = get_provider(self.config.provider, **provider_kwargs)
        self._system_prompt = self._build_initial_system_prompt()

    def _build_initial_system_prompt(self) -> str:
        from ohmycode.memory.backend import (
            auto_import_memory_backends,
            get_memory_backend,
            get_project_memory_dir,
        )

        cwd = os.getcwd()
        project_instructions = find_project_instructions(cwd)

        auto_import_memory_backends()

        mem_dir = ""
        memory_content = ""
        try:
            mem_dir = get_project_memory_dir(cwd)
            store = get_memory_backend(self.config.memory_backend, memory_dir=mem_dir)
            store.ensure_tree()
            memory_content = store.get_root_index()
        except Exception as exc:
            print(
                f"[memory] store unavailable: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            mem_dir = ""
            memory_content = ""

        return build_system_prompt(
            mode=self.config.mode,
            cwd=cwd,
            project_instructions=project_instructions,
            memory_content=memory_content,
            memory_dir=mem_dir,
            system_prompt_append=self.config.system_prompt_append,
        )

    def add_user_message(
        self, content: str, image_blocks: list[ImageBlock] | None = None
    ) -> None:
        """Append a user message to conversation history."""
        if image_blocks:
            self.messages.append(UserMessage(content=[content] + image_blocks))
        else:
            self.messages.append(UserMessage(content=content))

    def cancel(self) -> None:
        """Set cancel flag so run_turn() exits on the next check."""
        self._cancelled = True

    def get_status_snapshot(self) -> dict[str, Any]:
        """Return current conversation/context usage stats for /status."""
        used_tokens = self.context_mgr.count_tokens(self.messages, self._system_prompt)
        effective_window = max(1, self.config.token_budget - self.config.output_tokens_reserved)
        usage_ratio = self.context_mgr.get_usage_ratio(self.messages, self._system_prompt)
        usage_percent = round(usage_ratio * 100, 1)

        if usage_ratio >= 0.90:
            compression_stage = "auto_compact"
        elif usage_ratio >= 0.85:
            compression_stage = "collapse"
        elif usage_ratio >= 0.80:
            compression_stage = "micro_compact"
        elif usage_ratio >= 0.75:
            compression_stage = "snip"
        else:
            compression_stage = "ok"

        return {
            "message_count": len(self.messages),
            "used_tokens": used_tokens,
            "token_budget": self.config.token_budget,
            "output_reserved": self.config.output_tokens_reserved,
            "effective_window": effective_window,
            "usage_ratio": usage_ratio,
            "usage_percent": usage_percent,
            "compression_stage": compression_stage,
            "mode": self.config.mode,
            "provider": self.config.provider,
            "model": self.config.model,
        }

    # ── Main loop ────────────────────────────────────────────────────────────

    async def run_turn(
        self,
        system_prompt_override: str | None = None,
        allow_blocking_compression: bool = True,
    ) -> AsyncIterator[StreamEvent]:
        """Run one conversation turn (may include multiple tool round-trips)."""
        self._cancelled = False
        turn_system_prompt = system_prompt_override or self._system_prompt
        turn_count = 0
        max_turns = self.config.max_turns

        tool_defs = get_tool_defs()

        # Tools (e.g. AgentTool) push StreamEvents into this buffer; the loop
        # flushes them out alongside ToolCallResult so the renderer can show
        # sub-agent progress without tools knowing about the UI layer.
        sub_event_buffer: list[StreamEvent] = []
        ctx = ToolContext(
            mode=self.config.mode,
            agent_depth=0,
            cwd=os.getcwd(),
            is_sub_agent=False,
            config=self.config,
            event_emitter=sub_event_buffer.append,
        )

        round_state = _RoundState()

        while turn_count < max_turns and not self._cancelled:
            turn_count += 1

            if not await self._compress(turn_system_prompt, allow_blocking_compression):
                yield TurnComplete(finish_reason="error", usage=TokenUsage(0, 0, 0))
                return

            try:
                async for ev in self._stream_one_round(
                    turn_system_prompt, tool_defs, round_state
                ):
                    yield ev
            except asyncio.CancelledError:
                if round_state.collected_text:
                    self.messages.append(
                        AssistantMessage(content=round_state.collected_text, tool_calls=[])
                    )
                yield TurnComplete(finish_reason="cancelled", usage=round_state.last_usage)
                raise
            except Exception as e:
                yield TextChunk(text=f"\n[API Error: {e}]\n")
                yield TurnComplete(finish_reason="error", usage=TokenUsage(0, 0, 0))
                return

            if self._cancelled:
                if round_state.collected_text:
                    self.messages.append(
                        AssistantMessage(content=round_state.collected_text, tool_calls=[])
                    )
                yield TurnComplete(finish_reason="cancelled", usage=round_state.last_usage)
                return

            self._record_assistant_message(round_state)

            if (
                not round_state.collected_tool_calls
                or round_state.last_finish_reason != "tool_use"
            ):
                yield TurnComplete(
                    finish_reason=round_state.last_finish_reason,
                    usage=round_state.last_usage,
                )
                return

            try:
                async for ev in self._authorize_and_execute(
                    round_state.collected_tool_calls, ctx, sub_event_buffer
                ):
                    yield ev
            except asyncio.CancelledError:
                yield TurnComplete(finish_reason="cancelled", usage=round_state.last_usage)
                raise

        yield TurnComplete(finish_reason="max_turns", usage=round_state.last_usage)

    # ── Phase helpers ────────────────────────────────────────────────────────

    async def _compress(self, turn_system_prompt: str, allow_llm: bool) -> bool:
        """Run compression if needed. Returns False on circuit-breaker error."""
        try:
            self.messages = await self._compression.maybe_compress(
                self.messages,
                turn_system_prompt,
                self._provider,
                self.config.model,
                allow_llm=allow_llm,
            )
            return True
        except RuntimeError:
            return False

    async def _stream_one_round(
        self,
        turn_system_prompt: str,
        tool_defs: list,
        round_state: _RoundState,
    ) -> AsyncIterator[StreamEvent]:
        """Stream one provider round; mutate round_state with what arrived."""
        round_state.collected_text = ""
        round_state.collected_tool_calls = []

        stream_kwargs: dict[str, Any] = {}
        if self.think:
            stream_kwargs["reasoning_effort"] = self.think

        async for event in self._provider.stream(
            messages=self.messages,
            tools=tool_defs,
            system=turn_system_prompt,
            model=self.config.model,
            **stream_kwargs,
        ):
            if self._cancelled:
                break

            if isinstance(event, TextChunk):
                round_state.collected_text += event.text
                yield event
            elif isinstance(event, ThinkingChunk):
                yield event
            elif isinstance(event, ToolCallStreaming):
                yield event
            elif isinstance(event, ToolCallStart):
                round_state.collected_tool_calls.append(event)
                yield event
            elif isinstance(event, TurnComplete):
                round_state.last_usage = event.usage
                round_state.last_finish_reason = event.finish_reason

    def _record_assistant_message(self, round_state: _RoundState) -> None:
        tool_use_blocks = [
            ToolUseBlock(
                tool_use_id=tc.tool_use_id,
                tool_name=tc.tool_name,
                params=tc.params,
            )
            for tc in round_state.collected_tool_calls
        ]
        self.messages.append(
            AssistantMessage(
                content=round_state.collected_text,
                tool_calls=tool_use_blocks,
            )
        )

    async def _authorize_and_execute(
        self,
        tool_calls: list[ToolCallStart],
        ctx: ToolContext,
        sub_event_buffer: list[StreamEvent],
    ) -> AsyncIterator[StreamEvent]:
        """Permission check + execute permitted calls; record results.

        On asyncio.CancelledError, fills placeholder results for any unanswered
        tool_call_ids and re-raises (caller emits the final TurnComplete).
        """
        responded_ids: set[str] = set()
        permitted_calls: list[dict] = []

        try:
            for tc in tool_calls:
                async for ev in self._authorize_one(
                    tc, permitted_calls, responded_ids
                ):
                    yield ev

            if not permitted_calls:
                return

            results = await run_tool_calls(permitted_calls, ctx)

            while sub_event_buffer:
                yield sub_event_buffer.pop(0)

            for call in permitted_calls:
                tid = call["tool_use_id"]
                tool_result = results[tid]
                self.messages.append(
                    ToolResultMessage(
                        tool_use_id=tid,
                        content=tool_result.output,
                        is_error=tool_result.is_error,
                    )
                )
                responded_ids.add(tid)
                yield ToolCallResult(
                    tool_use_id=tid,
                    result=tool_result.output,
                    is_error=tool_result.is_error,
                )
        except asyncio.CancelledError:
            for tc in tool_calls:
                if tc.tool_use_id not in responded_ids:
                    self.messages.append(
                        ToolResultMessage(
                            tool_use_id=tc.tool_use_id,
                            content="Cancelled by user.",
                            is_error=False,
                        )
                    )
            raise

    async def _authorize_one(
        self,
        tc: ToolCallStart,
        permitted_calls: list[dict],
        responded_ids: set[str],
    ) -> AsyncIterator[StreamEvent]:
        """Run the permission ladder for a single tool call."""
        perm = check_permission(
            tool_name=tc.tool_name,
            params=tc.params,
            mode=self.config.mode,
            rules=self.config.rules,
            auto_approved=self.auto_approved,
        )

        call_dict = {
            "tool_name": tc.tool_name,
            "tool_use_id": tc.tool_use_id,
            "params": tc.params,
        }

        if perm.action == "deny":
            error_msg = f"Permission denied: {perm.reason}"
            self._record_tool_error(tc.tool_use_id, error_msg, responded_ids)
            yield ToolCallResult(
                tool_use_id=tc.tool_use_id, result=error_msg, is_error=True
            )
            return

        if perm.action == "ask" and self.confirm_fn is not None:
            answer = (await self.confirm_fn(tc.tool_name, tc.params)).strip().lower()
            if answer == "a":
                self.auto_approved[tc.tool_name] = True
                permitted_calls.append(call_dict)
            elif answer == "y":
                permitted_calls.append(call_dict)
            else:
                error_msg = "User denied tool execution."
                self._record_tool_error(tc.tool_use_id, error_msg, responded_ids)
                yield ToolCallResult(
                    tool_use_id=tc.tool_use_id, result=error_msg, is_error=True
                )
            return

        # allow (or "ask" without confirm_fn)
        permitted_calls.append(call_dict)

    def _record_tool_error(
        self, tool_use_id: str, message: str, responded_ids: set[str]
    ) -> None:
        self.messages.append(
            ToolResultMessage(
                tool_use_id=tool_use_id,
                content=message,
                is_error=True,
            )
        )
        responded_ids.add(tool_use_id)
