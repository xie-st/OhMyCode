"""Agent tool — spawn a sub-agent for subtasks.

Sub-agent progress is emitted via `ctx.event_emitter` as `SubAgentToolUse` /
`SubAgentDone` events. The renderer (in `_cli/output.py`) is responsible for
turning those into a panel; this module deliberately does not import any UI.
"""

from __future__ import annotations

import copy

from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.messages import (
    SubAgentDone,
    SubAgentToolUse,
    TextChunk,
    ToolCallStart,
)
from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool

MAX_AGENT_DEPTH = 2
_OUTPUT_CHAR_LIMIT = 10000


def _emit(ctx: ToolContext, event) -> None:
    """Best-effort event emission; swallows emitter exceptions so tool exec is unaffected."""
    if ctx.event_emitter is None:
        return
    try:
        ctx.event_emitter(event)
    except Exception:
        pass


@register_tool
class AgentTool(Tool):
    name = "agent"
    description = (
        "Spawn a sub-agent for a subtask with its own context. Max depth: 2."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Prompt sent to the sub-agent",
            },
        },
        "required": ["prompt"],
    }
    concurrent_safe = False

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        prompt = params["prompt"]

        if ctx.agent_depth >= MAX_AGENT_DEPTH:
            return ToolResult(
                output=f"Agent depth limit ({MAX_AGENT_DEPTH}) exceeded.",
                is_error=True,
            )

        # Imported here to avoid a circular dep with core.loop at module load time.
        from ohmycode.core.loop import ConversationLoop

        config = copy.copy(ctx.config) if ctx.config is not None else OhMyCodeConfig()
        config.mode = ctx.mode

        sub_loop = ConversationLoop(config)
        sub_loop.initialize()
        sub_loop.add_user_message(prompt)

        collected_text = ""
        try:
            async for event in sub_loop.run_turn():
                if isinstance(event, TextChunk):
                    collected_text += event.text
                elif isinstance(event, ToolCallStart):
                    _emit(ctx, SubAgentToolUse(tool_name=event.tool_name))
        except Exception as exc:
            _emit(ctx, SubAgentDone(is_error=True))
            return ToolResult(output=f"Sub-agent error: {exc}", is_error=True)

        _emit(ctx, SubAgentDone(is_error=False))

        if len(collected_text) > _OUTPUT_CHAR_LIMIT:
            collected_text = collected_text[:_OUTPUT_CHAR_LIMIT]

        return ToolResult(output=collected_text, is_error=False)
