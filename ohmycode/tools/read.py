"""Read tool — read file contents with optional line offset and limit."""

from __future__ import annotations

from pathlib import Path

from ohmycode.core.file_utils import read_lines_numbered
from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool


@register_tool
class ReadTool(Tool):
    name = "read"
    description = (
        "Read a file and return numbered lines. Supports offset and limit to bound the range."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path of the file to read",
            },
            "offset": {
                "type": "integer",
                "description": "Start reading from this line (1-indexed, default 1)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read (default: entire file)",
            },
        },
        "required": ["file_path"],
    }
    concurrent_safe = True

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        file_path = Path(params["file_path"])
        offset = max(1, int(params.get("offset", 1)))
        limit = params.get("limit")

        try:
            numbered, _ = read_lines_numbered(file_path, offset=offset, limit=limit)
        except FileNotFoundError:
            return ToolResult(output=f"File not found: {file_path}", is_error=True)
        except Exception as exc:
            return ToolResult(output=f"Error reading file: {exc}", is_error=True)

        return ToolResult(output=numbered, is_error=False)
