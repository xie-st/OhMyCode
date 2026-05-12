"""``CompressionStrategy`` protocol + registry."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from ohmycode.core.messages import Message


@runtime_checkable
class CompressionStrategy(Protocol):
    """A strategy decides when (and how) to compress a message list."""

    async def maybe_compress(
        self,
        messages: list[Message],
        system_prompt: str,
        provider: Any,
        model: str,
        *,
        allow_llm: bool = True,
    ) -> list[Message]: ...


_STRATEGY_REGISTRY: dict[str, Callable[..., CompressionStrategy]] = {}


def register_compression_strategy(
    name: str, factory: Callable[..., CompressionStrategy]
) -> None:
    _STRATEGY_REGISTRY[name] = factory


def get_compression_strategy(name: str, **kwargs: Any) -> CompressionStrategy:
    if name not in _STRATEGY_REGISTRY:
        raise ValueError(
            f"Unknown compression strategy: '{name}'. "
            f"Available: {list(_STRATEGY_REGISTRY.keys())}"
        )
    return _STRATEGY_REGISTRY[name](**kwargs)


def auto_import_compression_strategies() -> None:
    """Import every sibling so registrations happen as a side effect."""
    package_dir = Path(__file__).parent
    skip = {"strategy", "__init__"}
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name in skip:
            continue
        importlib.import_module(f"ohmycode.core.compression.{module_info.name}")
