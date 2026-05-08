"""Default tiered compression strategy (75/80/85/90 thresholds).

``ContextManager`` already implements the four-tier algorithm and matches
the ``CompressionStrategy`` shape, so the registry simply hands its
constructor to callers. ``TieredCompressionStrategy`` is exposed as an
alias for documentation and ``isinstance`` clarity.

Each instance owns its own ``ContextManager`` so the LLM-failure circuit
breaker is per-loop — sub-agents do not trip their parent's breaker.
"""

from __future__ import annotations

from ohmycode.core.compression.strategy import register_compression_strategy
from ohmycode.core.context import ContextManager


# An alias name keeps ``isinstance(strategy, TieredCompressionStrategy)``
# working while collapsing the redundant wrapper class.
TieredCompressionStrategy = ContextManager


register_compression_strategy("tiered", ContextManager)
