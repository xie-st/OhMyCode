"""Grep tool — search file contents with a regular expression."""

from __future__ import annotations

import re
from pathlib import Path

from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool

_MAX_RESULTS = 200


@register_tool
class GrepTool(Tool):
    name = "grep"
    description = (
        "Search files for a regex pattern; output as filepath:line:content, max 200 matches."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression pattern",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search (defaults to ctx.cwd)",
            },
            "glob": {
                "type": "string",
                "description": "Glob to limit files searched (e.g. '*.py')",
            },
            "-i": {
                "type": "boolean",
                "description": "Case-insensitive search (default false)",
            },
        },
        "required": ["pattern"],
    }
    concurrent_safe = True

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        pattern_str: str = params["pattern"]
        base = Path(params.get("path") or ctx.cwd)
        glob_pat: str = params.get("glob", "**/*")
        case_insensitive: bool = params.get("-i", False)

        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern_str, flags)
        except re.error as exc:
            return ToolResult(output=f"Invalid regex: {exc}", is_error=True)

        # Collect candidate files
        if base.is_file():
            files = [base]
        else:
            try:
                files = [p for p in base.glob(glob_pat) if p.is_file()]
            except Exception as exc:
                return ToolResult(output=f"Glob error: {exc}", is_error=True)

        matches: list[str] = []
        for file_path in files:
            try:
                lines = file_path.read_text(errors="replace").splitlines()
            except Exception:
                continue
            for lineno, line in enumerate(lines, start=1):
                if regex.search(line):
                    matches.append(f"{file_path}:{lineno}:{line}")
                    if len(matches) >= _MAX_RESULTS:
                        break
            if len(matches) >= _MAX_RESULTS:
                break

        if not matches:
            return ToolResult(output="No matches found.", is_error=False)

        return ToolResult(output="\n".join(matches), is_error=False)
