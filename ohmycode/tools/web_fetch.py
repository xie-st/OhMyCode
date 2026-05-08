"""WebFetch tool — fetch URL content."""

from __future__ import annotations

import httpx

from ohmycode.tools._common import strip_html
from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool


@register_tool
class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch a URL and return its body as text."
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to fetch",
            },
        },
        "required": ["url"],
    }
    concurrent_safe = True

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        url = params["url"]

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                response = await client.get(url)
                response.raise_for_status()

            content = response.text

            content_type = response.headers.get("content-type", "").lower()
            if "html" in content_type:
                content = strip_html(content)

            if len(content) > 50000:
                content = content[:50000]

            return ToolResult(output=content, is_error=False)

        except httpx.RequestError as exc:
            return ToolResult(output=f"Network error: {exc}", is_error=True)
        except Exception as exc:
            return ToolResult(output=f"Error fetching URL: {exc}", is_error=True)
