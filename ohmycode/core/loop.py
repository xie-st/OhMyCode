"""Async conversation loop with tool execution and permission checks."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import AsyncIterator, Callable, Awaitable, Any

from ohmycode.core.messages import (
    UserMessage,
    AssistantMessage,
    ToolResultMessage,
    ToolUseBlock,
    TextChunk,
    ThinkingChunk,
    ToolCallStreaming,
    ToolCallStart,
    ToolCallResult,
    TurnComplete,
    TokenUsage,
    StreamEvent,
    Message,
    ImageBlock,
)
from ohmycode.core.context import ContextManager
from ohmycode.core.permissions import check_permission
from ohmycode.core.system_prompt import build_system_prompt, find_project_instructions
from ohmycode.providers.base import get_provider, auto_import_providers
from ohmycode.tools.base import auto_import_tools, get_tool_defs, run_tool_calls, ToolContext
from ohmycode.config.config import OhMyCodeConfig


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
        self.context_mgr = ContextManager(
            token_budget=config.token_budget,
            output_reserved=config.output_tokens_reserved,
        )

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

        from ohmycode.memory.memory import BTreeMemoryStore, get_project_memory_dir

        cwd = os.getcwd()
        project_instructions = find_project_instructions(cwd)

        mem_dir = ""
        memory_content = ""
        try:
            mem_dir = get_project_memory_dir(cwd)
            store = BTreeMemoryStore(mem_dir)
            store.ensure_tree()
            memory_content = store.get_root_index()
        except Exception as exc:
            print(
                f"[memory] store unavailable: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            mem_dir = ""
            memory_content = ""

        self._system_prompt = build_system_prompt(
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

    async def run_turn(
        self,
        system_prompt_override: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run one conversation turn (may include multiple tool round-trips).

        Yields StreamEvent for the caller (CLI) to render.
        """
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

        # Latest usage (updated after each provider call)
        last_usage = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        last_finish_reason = "stop"

        while turn_count < max_turns and not self._cancelled:
            turn_count += 1

            # ── Context compression (if needed) ────────────────────────────────
            try:
                self.messages = await self.context_mgr.maybe_compress(
                    self.messages, turn_system_prompt, self._provider, self.config.model
                )
            except RuntimeError:
                yield TurnComplete(finish_reason="error", usage=TokenUsage(0, 0, 0))
                return

            # ── Call provider.stream() ───────────────────────────────────────
            collected_text = ""
            collected_tool_calls: list[ToolCallStart] = []

            try:
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
                        collected_text += event.text
                        yield event

                    elif isinstance(event, ThinkingChunk):
                        yield event

                    elif isinstance(event, ToolCallStreaming):
                        yield event

                    elif isinstance(event, ToolCallStart):
                        collected_tool_calls.append(event)
                        yield event

                    elif isinstance(event, TurnComplete):
                        last_usage = event.usage
                        last_finish_reason = event.finish_reason
            except asyncio.CancelledError:
                # render_stream task was cancelled by Ctrl+C — save partial reply
                if collected_text:
                    self.messages.append(AssistantMessage(content=collected_text, tool_calls=[]))
                yield TurnComplete(finish_reason="cancelled", usage=last_usage)
                raise
            except Exception as e:
                yield TextChunk(text=f"\n[API Error: {e}]\n")
                yield TurnComplete(finish_reason="error", usage=TokenUsage(0, 0, 0))
                return

            # ── Handle cancellation via flag (conv.cancel() path) ─────────────
            if self._cancelled:
                if collected_text:
                    self.messages.append(AssistantMessage(content=collected_text, tool_calls=[]))
                yield TurnComplete(finish_reason="cancelled", usage=last_usage)
                return

            # ── Record assistant message ───────────────────────────────────────
            tool_use_blocks = [
                ToolUseBlock(
                    tool_use_id=tc.tool_use_id,
                    tool_name=tc.tool_name,
                    params=tc.params,
                )
                for tc in collected_tool_calls
            ]
            self.messages.append(
                AssistantMessage(
                    content=collected_text,
                    tool_calls=tool_use_blocks,
                )
            )

            # ── No tool calls or non-tool_use finish: end turn ─────────────────
            if not collected_tool_calls or last_finish_reason != "tool_use":
                yield TurnComplete(finish_reason=last_finish_reason, usage=last_usage)
                return

            # ── Permission checks + tool execution ────────────────────────────
            # Track which tool_call_ids already have a ToolResultMessage so we
            # can fill in the blanks if the task is cancelled mid-way.
            responded_ids: set[str] = set()
            permitted_calls: list[dict] = []

            try:
                for tc in collected_tool_calls:
                    perm = check_permission(
                        tool_name=tc.tool_name,
                        params=tc.params,
                        mode=self.config.mode,
                        rules=self.config.rules,
                        auto_approved=self.auto_approved,
                    )

                    if perm.action == "deny":
                        error_msg = f"Permission denied: {perm.reason}"
                        self.messages.append(
                            ToolResultMessage(
                                tool_use_id=tc.tool_use_id,
                                content=error_msg,
                                is_error=True,
                            )
                        )
                        responded_ids.add(tc.tool_use_id)
                        yield ToolCallResult(
                            tool_use_id=tc.tool_use_id,
                            result=error_msg,
                            is_error=True,
                        )
                        continue

                    if perm.action == "ask" and self.confirm_fn is not None:
                        answer = await self.confirm_fn(tc.tool_name, tc.params)
                        answer = answer.strip().lower()
                        if answer == "a":
                            # Auto-approve this tool for the rest of the session
                            self.auto_approved[tc.tool_name] = True
                            permitted_calls.append(
                                {
                                    "tool_name": tc.tool_name,
                                    "tool_use_id": tc.tool_use_id,
                                    "params": tc.params,
                                }
                            )
                        elif answer == "y":
                            permitted_calls.append(
                                {
                                    "tool_name": tc.tool_name,
                                    "tool_use_id": tc.tool_use_id,
                                    "params": tc.params,
                                }
                            )
                        else:
                            # User denied
                            error_msg = "User denied tool execution."
                            self.messages.append(
                                ToolResultMessage(
                                    tool_use_id=tc.tool_use_id,
                                    content=error_msg,
                                    is_error=True,
                                )
                            )
                            responded_ids.add(tc.tool_use_id)
                            yield ToolCallResult(
                                tool_use_id=tc.tool_use_id,
                                result=error_msg,
                                is_error=True,
                            )
                    else:
                        # allow (or run ask without confirm_fn)
                        permitted_calls.append(
                            {
                                "tool_name": tc.tool_name,
                                "tool_use_id": tc.tool_use_id,
                                "params": tc.params,
                            }
                        )

                # ── Execute permitted tool calls ───────────────────────────────
                if permitted_calls:
                    results = await run_tool_calls(permitted_calls, ctx)

                    # Flush any sub-agent events that tools pushed during execution.
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
                # Fill in placeholder results for any tool_calls without a response
                for tc in collected_tool_calls:
                    if tc.tool_use_id not in responded_ids:
                        self.messages.append(
                            ToolResultMessage(
                                tool_use_id=tc.tool_use_id,
                                content="Cancelled by user.",
                                is_error=False,
                            )
                        )
                yield TurnComplete(finish_reason="cancelled", usage=last_usage)
                raise

            # Continue loop: model sees tool results and produces next reply

        # Exceeded max_turns
        yield TurnComplete(
            finish_reason="max_turns",
            usage=last_usage,
        )
