"""Agent tool — spawn a sub-agent for subtasks."""

from __future__ import annotations

from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool

MAX_AGENT_DEPTH = 2
_OUTPUT_CHAR_LIMIT = 10000


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

        # Enforce depth limit
        if ctx.agent_depth >= MAX_AGENT_DEPTH:
            return ToolResult(
                output=f"Agent depth limit ({MAX_AGENT_DEPTH}) exceeded.",
                is_error=True,
            )

        # Lazy imports to avoid circular imports
        import asyncio
        import sys
        import time
        from ohmycode.core.loop import ConversationLoop
        from ohmycode.config.config import OhMyCodeConfig
        from ohmycode._cli.output import SubAgentBox, _is_interactive, _spinner_task, _cancel_spinner
        from ohmycode.core.messages import TextChunk, ToolCallStart

        try:
            import copy
            if ctx.config is not None:
                config = copy.copy(ctx.config)
            else:
                config = OhMyCodeConfig()
            config.mode = ctx.mode

            should_render = _is_interactive() and ctx.agent_depth == 0
            box = SubAgentBox() if should_render else None

            # Spinner shown from initialization through the first tool call
            spinner_task = None
            if box is not None:
                spinner_task = asyncio.create_task(
                    _spinner_task("Sub-agent starting...", time.monotonic())
                )

            sub_loop = ConversationLoop(config)
            sub_loop.initialize()
            sub_loop.add_user_message(prompt)

            collected_text = ""
            error_result = None
            try:
                async for event in sub_loop.run_turn():
                    if isinstance(event, TextChunk):
                        collected_text += event.text
                    elif isinstance(event, ToolCallStart) and box is not None:
                        await _cancel_spinner(spinner_task)
                        box.push_tool(event.tool_name)
            except Exception as exc:
                error_result = ToolResult(
                    output=f"Sub-agent error: {exc}",
                    is_error=True,
                )
            finally:
                await _cancel_spinner(spinner_task)
                if box is not None:
                    if error_result is None:
                        box.finish()
                    else:
                        box.clear()

            if error_result is not None:
                return error_result

            if len(collected_text) > _OUTPUT_CHAR_LIMIT:
                collected_text = collected_text[:_OUTPUT_CHAR_LIMIT]

            return ToolResult(output=collected_text, is_error=False)

        except Exception as exc:
            return ToolResult(output=f"Error spawning agent: {exc}", is_error=True)
