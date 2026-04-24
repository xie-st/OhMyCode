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

        # Lazy imports to avoid circular imports
        import asyncio
        import sys
        import time
        from ohmycode.core.loop import ConversationLoop
        from ohmycode.config.config import OhMyCodeConfig
        from ohmycode._cli.output import SubAgentBox, _is_interactive
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
                _SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                _t_start = time.monotonic()

                async def _spinner():
                    idx = 0
                    try:
                        while True:
                            elapsed = time.monotonic() - _t_start
                            frame = _SPINNER_FRAMES[idx % len(_SPINNER_FRAMES)]
                            sys.stdout.write(
                                f"\r  \033[2m{frame} Sub-agent starting... {elapsed:.0f}s\033[0m\033[K"
                            )
                            sys.stdout.flush()
                            idx += 1
                            await asyncio.sleep(0.1)
                    except asyncio.CancelledError:
                        sys.stdout.write("\r\033[K")
                        sys.stdout.flush()

                spinner_task = asyncio.create_task(_spinner())

            async def _cancel_spinner():
                nonlocal spinner_task
                if spinner_task and not spinner_task.done():
                    spinner_task.cancel()
                    try:
                        await spinner_task
                    except asyncio.CancelledError:
                        pass
                    spinner_task = None

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
                        await _cancel_spinner()
                        box.push_tool(event.tool_name)
            except Exception as exc:
                error_result = ToolResult(
                    output=f"Sub-agent error: {exc}",
                    is_error=True,
                )
            finally:
                await _cancel_spinner()
                if box is not None:
                    if error_result is None:
                        box.finish()
                    else:
                        box.clear()

            if error_result is not None:
                return error_result

            # Truncate to 10000 characters
            if len(collected_text) > 10000:
                collected_text = collected_text[:10000]

            return ToolResult(output=collected_text, is_error=False)

        except Exception as exc:
            return ToolResult(output=f"Error spawning agent: {exc}", is_error=True)
