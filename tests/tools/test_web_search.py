from unittest.mock import patch

import httpx
import pytest
from ohmycode.tools.base import ToolContext
from ohmycode.tools.web_search import WebSearchTool, _detect_proxy


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(mode="auto", agent_depth=0, cwd=str(tmp_path), is_sub_agent=False)


@pytest.mark.asyncio
async def test_web_search_tool_properties(ctx):
    """Test that WebSearchTool has correct properties."""
    tool = WebSearchTool()
    assert tool.name == "web_search"
    assert tool.concurrent_safe is True
    assert "query" in tool.parameters["properties"]


def test_detect_proxy_prefers_ohmycode_proxy(monkeypatch):
    monkeypatch.setenv("OHMYCODE_PROXY", "http://ohmy:1111")
    monkeypatch.setenv("HTTPS_PROXY", "http://other:2222")
    assert _detect_proxy() == "http://ohmy:1111"


def test_detect_proxy_falls_back_to_https_proxy(monkeypatch):
    monkeypatch.delenv("OHMYCODE_PROXY", raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://https:2222")
    assert _detect_proxy() == "http://https:2222"


def test_detect_proxy_none_when_unset(monkeypatch):
    for var in ("OHMYCODE_PROXY", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(var, raising=False)
    assert _detect_proxy() is None


@pytest.mark.asyncio
async def test_web_search_passes_proxy_to_client(ctx, monkeypatch):
    """When OHMYCODE_PROXY is set, it must be forwarded to httpx.AsyncClient."""
    monkeypatch.setenv("OHMYCODE_PROXY", "http://127.0.0.1:7890")

    captured_kwargs = {}
    original_init = httpx.AsyncClient.__init__

    def spy_init(self, *args, **kwargs):
        captured_kwargs.update(kwargs)
        return original_init(self, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "__init__", spy_init):
        # Make the actual GET fail fast — we only care about client construction.
        async def fake_get(self, *args, **kwargs):
            raise httpx.ConnectError("forced")

        with patch.object(httpx.AsyncClient, "get", fake_get):
            result = await WebSearchTool().execute({"query": "test"}, ctx)

    assert captured_kwargs.get("proxy") == "http://127.0.0.1:7890"
    assert result.is_error is True
    assert "OHMYCODE_PROXY" in result.output


@pytest.mark.asyncio
async def test_web_search_no_proxy_when_env_empty(ctx, monkeypatch):
    """When no proxy env vars are set, `proxy` must not be passed to AsyncClient."""
    for var in ("OHMYCODE_PROXY", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(var, raising=False)

    captured_kwargs = {}
    original_init = httpx.AsyncClient.__init__

    def spy_init(self, *args, **kwargs):
        captured_kwargs.update(kwargs)
        return original_init(self, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "__init__", spy_init):
        async def fake_get(self, *args, **kwargs):
            raise httpx.ConnectError("forced")

        with patch.object(httpx.AsyncClient, "get", fake_get):
            await WebSearchTool().execute({"query": "test"}, ctx)

    assert "proxy" not in captured_kwargs


@pytest.mark.asyncio
async def test_web_search_connect_error_gives_proxy_hint(ctx, monkeypatch):
    """ConnectError should produce a user-friendly proxy hint."""
    for var in ("OHMYCODE_PROXY", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(var, raising=False)

    async def fake_get(self, *args, **kwargs):
        raise httpx.ConnectError("name resolution failed")

    with patch.object(httpx.AsyncClient, "get", fake_get):
        result = await WebSearchTool().execute({"query": "test"}, ctx)

    assert result.is_error is True
    assert "Connection failed" in result.output
    assert "OHMYCODE_PROXY" in result.output
