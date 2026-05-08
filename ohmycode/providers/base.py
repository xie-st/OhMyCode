"""Provider protocol, base class, and registry.

Each concrete provider lives in its own module under ``ohmycode/providers/``
and registers itself via ``register_provider`` (typically through
``BaseProvider`` subclassing).
"""

from __future__ import annotations

import asyncio
import importlib
import json
import pkgutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol, runtime_checkable

from ohmycode.core.messages import (
    Message,
    StreamEvent,
    TokenUsage,
    ToolCallStart,
    TurnComplete,
)


class ToolDef:
    """Tool definition sent to the LLM API."""

    def __init__(self, name: str, description: str, parameters: dict):
        self.name = name
        self.description = description
        self.parameters = parameters

    def to_api_dict(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ── Protocol (for duck-typed callers / tests) ────────────────────────────────


@runtime_checkable
class Provider(Protocol):
    name: str

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        system: str,
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]: ...


# ── Base class with shared retry + emission helpers ──────────────────────────


class BaseProvider(ABC):
    """Concrete providers should subclass this to inherit retry + tool-call emission.

    Subclasses must define ``name`` and implement ``stream``. Inside ``stream``
    they should use ``self._with_retry`` to establish the network call, then
    iterate the SDK stream and finally call ``self._emit_tool_calls`` and
    ``self._make_turn_complete`` to produce the trailing events.
    """

    name: str = ""

    # Shared retry policy. Subclasses override ``_RETRYABLE`` to declare which
    # exception types trigger a retry; the base sleeps via ``_RETRY_DELAYS``.
    _MAX_RETRIES: int = 3
    _RETRY_DELAYS: tuple[int, ...] = (1, 2, 5)

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        system: str,
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        ...

    def _is_retryable(self, exc: BaseException) -> bool:
        """Return True if ``exc`` should trigger a retry. Subclass to customize."""
        return False

    async def _with_retry(self, factory: Callable[[], Awaitable[Any]]) -> Any:
        """Call ``factory()`` with retries on retryable errors."""
        last_exc: BaseException | None = None
        for attempt in range(self._MAX_RETRIES):
            try:
                return await factory()
            except BaseException as exc:  # noqa: BLE001 — re-raised below
                if attempt < self._MAX_RETRIES - 1 and self._is_retryable(exc):
                    delay = self._RETRY_DELAYS[
                        min(attempt, len(self._RETRY_DELAYS) - 1)
                    ]
                    await asyncio.sleep(delay)
                    last_exc = exc
                    continue
                raise
        # Unreachable, but keep the type-checker happy
        if last_exc:
            raise last_exc
        raise RuntimeError("retry loop exited without success or exception")

    @staticmethod
    def _emit_tool_calls(tool_calls_acc: dict[int, dict]) -> list[ToolCallStart]:
        """Convert accumulated tool-call deltas into ToolCallStart events.

        ``tool_calls_acc`` maps an index to a dict with keys ``id``, ``name``,
        ``arguments`` (the partial JSON string).
        """
        events: list[ToolCallStart] = []
        for idx in sorted(tool_calls_acc.keys()):
            tc = tool_calls_acc[idx]
            try:
                params = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                params = {"_raw": tc["arguments"]}
            events.append(
                ToolCallStart(
                    tool_name=tc["name"],
                    tool_use_id=tc["id"],
                    params=params,
                )
            )
        return events

    @staticmethod
    def _make_turn_complete(
        finish_reason: str, prompt_tokens: int, completion_tokens: int
    ) -> TurnComplete:
        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0
        return TurnComplete(
            finish_reason=finish_reason,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )


# ── Registry + discovery ─────────────────────────────────────────────────────


PROVIDER_REGISTRY: dict[str, type] = {}


def register_provider(name: str, cls: type) -> None:
    PROVIDER_REGISTRY[name] = cls


def get_provider(name: str, **kwargs: Any) -> Any:
    if name not in PROVIDER_REGISTRY:
        raise ValueError(
            f"Unknown provider: '{name}'. Available: {list(PROVIDER_REGISTRY.keys())}"
        )
    return PROVIDER_REGISTRY[name](**kwargs)


def auto_import_providers() -> None:
    package_dir = Path(__file__).parent
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name not in {"base", "_streaming_utils"}:
            importlib.import_module(f"ohmycode.providers.{module_info.name}")


# ── Backwards-compatible re-exports ──────────────────────────────────────────
# ``stream_to_text`` / ``stream_to_box`` moved to ``_streaming_utils`` because
# they are caller-side helpers, not part of the provider surface. Re-exported
# here so existing imports (and the patched test in test_compressors.py)
# continue to work.

from ohmycode.providers._streaming_utils import (  # noqa: E402
    stream_to_box,
    stream_to_text,
)

__all__ = [
    "BaseProvider",
    "PROVIDER_REGISTRY",
    "Provider",
    "ToolDef",
    "auto_import_providers",
    "get_provider",
    "register_provider",
    "stream_to_box",
    "stream_to_text",
]
