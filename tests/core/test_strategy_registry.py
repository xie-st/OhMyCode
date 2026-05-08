"""Tests for the compression-strategy registry."""

from __future__ import annotations

import pytest

from ohmycode.core.compression import (
    CompressionStrategy,
    TieredCompressionStrategy,
    auto_import_compression_strategies,
    get_compression_strategy,
    register_compression_strategy,
)


def test_tiered_resolves_via_registry():
    auto_import_compression_strategies()
    strategy = get_compression_strategy(
        "tiered", token_budget=1000, output_reserved=200
    )
    assert isinstance(strategy, TieredCompressionStrategy)


def test_unknown_strategy_raises():
    with pytest.raises(ValueError) as exc_info:
        get_compression_strategy(
            "nonexistent", token_budget=1000, output_reserved=200
        )
    assert "Unknown compression strategy" in str(exc_info.value)


def test_strategy_protocol_satisfied():
    auto_import_compression_strategies()
    strategy = get_compression_strategy(
        "tiered", token_budget=1000, output_reserved=200
    )
    assert isinstance(strategy, CompressionStrategy)


def test_two_strategies_have_independent_state():
    """Two tiered strategies must not share circuit-breaker state."""
    a = get_compression_strategy("tiered", token_budget=1000, output_reserved=200)
    b = get_compression_strategy("tiered", token_budget=1000, output_reserved=200)
    a._failure_count = 5
    assert b._failure_count == 0


def test_custom_strategy_can_register():
    class _Stub:
        async def maybe_compress(self, messages, system_prompt, provider, model, *, allow_llm=True):
            return list(messages)

    register_compression_strategy("stub", lambda **kw: _Stub())
    strategy = get_compression_strategy("stub")
    assert isinstance(strategy, _Stub)
