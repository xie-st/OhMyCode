"""Write tool — create or overwrite file contents."""

from __future__ import annotations

from pathlib import Path

from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool


@register_tool
class WriteTool(Tool):
    name = "write"
    description = "Create a new file or overwrite an existing one."
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path of the file",
            },
            "content": {
                "type": "string",
                "description": "Content to write",
            },
        },
        "required": ["file_path", "content"],
    }
    concurrent_safe = False

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        file_path = Path(params["file_path"])
        content = params["content"]

        try:
            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            file_path.write_text(content, encoding="utf-8")

            # Return character count written
            return ToolResult(
                output=f"Wrote {len(content)} characters to {file_path}",
                is_error=False,
                metadata={"chars_written": len(content)},
            )
        except Exception as exc:
            return ToolResult(output=f"Error writing file: {exc}", is_error=True)
