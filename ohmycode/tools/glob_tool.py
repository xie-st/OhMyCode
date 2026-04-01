"""Glob tool — match file paths by pattern, sorted by modification time."""

from __future__ import annotations

from pathlib import Path

from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool

_MAX_RESULTS = 200


@register_tool
class GlobTool(Tool):
    name = "glob"
    description = (
        "Search files by glob pattern; results sorted by mtime descending, max 200."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern, e.g. '**/*.py'",
            },
            "path": {
                "type": "string",
                "description": "Root directory to search (defaults to ctx.cwd)",
            },
        },
        "required": ["pattern"],
    }
    concurrent_safe = True

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        pattern: str = params["pattern"]
        base = Path(params.get("path") or ctx.cwd)

        try:
            matches = list(base.glob(pattern))
        except Exception as exc:
            return ToolResult(output=f"Glob error: {exc}", is_error=True)

        # Sort by mtime descending
        matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        matches = matches[:_MAX_RESULTS]

        if not matches:
            return ToolResult(output="No files matched.", is_error=False)

        output = "\n".join(str(p) for p in matches)
        return ToolResult(output=output, is_error=False)
