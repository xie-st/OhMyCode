"""Agent tool — spawn a sub-agent for subtasks."""

from __future__ import annotations

from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool

MAX_AGENT_DEPTH = 2


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

        # Lazy import to avoid circular imports
        from ohmycode.core.loop import ConversationLoop
        from ohmycode.config.config import OhMyCodeConfig

        try:
            # Sub-agent config and loop
            config = OhMyCodeConfig()
            # Inherit mode
            config.mode = ctx.mode

            sub_loop = ConversationLoop(config)
            sub_loop.initialize()

            # New context with incremented depth
            sub_ctx = ToolContext(
                mode=ctx.mode,
                agent_depth=ctx.agent_depth + 1,
                cwd=ctx.cwd,
                is_sub_agent=True,
                extra=ctx.extra.copy() if ctx.extra else {},
            )

            # Add user message to sub-agent
            sub_loop.add_user_message(prompt)

            # Run sub-agent
            collected_text = ""
            try:
                async for event in sub_loop.run_turn():
                    from ohmycode.core.messages import TextChunk

                    if isinstance(event, TextChunk):
                        collected_text += event.text
            except Exception as exc:
                return ToolResult(
                    output=f"Sub-agent error: {exc}",
                    is_error=True,
                )

            # Truncate to 10000 characters
            if len(collected_text) > 10000:
                collected_text = collected_text[:10000]

            return ToolResult(output=collected_text, is_error=False)

        except Exception as exc:
            return ToolResult(output=f"Error spawning agent: {exc}", is_error=True)
