"""Pluggable context-compression strategies.

This package exposes a ``CompressionStrategy`` protocol plus a small
registry. The default ``TieredCompressionStrategy`` mirrors the four-level
threshold logic that has lived on ``ContextManager`` since the beginning;
new strategies (e.g. summarise-everything-on-overflow) plug in via
``register_compression_strategy``.

``ContextManager`` itself remains the home of token counting. Strategies
own the *policy* (when and how to compress); ``ContextManager`` owns the
*measurement* (how many tokens are we using).
"""

from __future__ import annotations

from ohmycode.core.compression.strategy import (
    CompressionStrategy,
    auto_import_compression_strategies,
    get_compression_strategy,
    register_compression_strategy,
)
from ohmycode.core.compression.tiered import TieredCompressionStrategy

__all__ = [
    "CompressionStrategy",
    "TieredCompressionStrategy",
    "auto_import_compression_strategies",
    "get_compression_strategy",
    "register_compression_strategy",
]
