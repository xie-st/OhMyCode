"""Edit tool — exact string replacement in a file."""

from __future__ import annotations

from pathlib import Path

from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool


@register_tool
class EditTool(Tool):
    name = "edit"
    description = (
        "Replace an exact substring in a file. old_string must occur exactly once."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path of the file to edit",
            },
            "old_string": {
                "type": "string",
                "description": "Substring to replace (must occur exactly once)",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text",
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }
    concurrent_safe = False

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        file_path = Path(params["file_path"])
        old_string: str = params["old_string"]
        new_string: str = params["new_string"]

        try:
            content = file_path.read_text(errors="replace")
        except FileNotFoundError:
            return ToolResult(output=f"File not found: {file_path}", is_error=True)
        except Exception as exc:
            return ToolResult(output=f"Error reading file: {exc}", is_error=True)

        count = content.count(old_string)
        if count == 0:
            return ToolResult(
                output=f"old_string not found in {file_path}",
                is_error=True,
            )
        if count > 1:
            return ToolResult(
                output=(
                    f"old_string appears {count} times in {file_path}; "
                    "it must appear exactly once."
                ),
                is_error=True,
            )

        new_content = content.replace(old_string, new_string, 1)
        try:
            file_path.write_text(new_content)
        except Exception as exc:
            return ToolResult(output=f"Error writing file: {exc}", is_error=True)

        return ToolResult(output=f"Replaced in {file_path}", is_error=False)
