"""Tool-authorization helpers extracted from ConversationLoop.

This module provides ``_AuthorizationMixin`` — the three coroutines that
walk the permission ladder, dispatch ``run_tool_calls``, and record
``ToolResultMessage`` entries for a turn. Splitting them out keeps
``core/loop.py`` focused on the streaming round-trip and stays under
the project's 500-line ceiling.

The mixin reads/writes the following attributes on the host class:

- ``self.config`` (``OhMyCodeConfig``) — mode + rules
- ``self.auto_approved`` (``dict[str, bool]``)
- ``self.confirm_fn`` — optional async user-confirm callback
- ``self.messages`` — appended with ``ToolResultMessage``
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from typing import Callable

from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.messages import (
    StreamEvent,
    ToolCallResult,
    ToolCallStart,
    ToolResultMessage,
)
from ohmycode.core.permissions import check_permission
from ohmycode.tools.base import ToolContext, run_tool_calls


class _AuthorizationMixin:
    """Permission check + dispatch for a batch of tool calls."""

    # Attributes provided by the host class. Declared here so type-checkers
    # know they exist; the actual values come from ``ConversationLoop``.
    config: OhMyCodeConfig
    auto_approved: dict[str, bool]
    confirm_fn: Callable[[str, dict], Awaitable[str]] | None
    messages: list

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
