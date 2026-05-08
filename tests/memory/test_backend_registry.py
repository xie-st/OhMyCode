"""Tests for the memory-backend registry introduced in the kernel-plugins refactor."""

from __future__ import annotations

import pytest

from ohmycode.memory.backend import (
    auto_import_memory_backends,
    get_memory_backend,
    register_memory_backend,
)
from ohmycode.memory.btree_backend import BTreeMemoryStore


def test_btree_resolves_via_registry(tmp_path):
    auto_import_memory_backends()
    backend = get_memory_backend("btree", memory_dir=tmp_path)
    assert isinstance(backend, BTreeMemoryStore)


def test_unknown_backend_raises():
    with pytest.raises(ValueError) as exc_info:
        get_memory_backend("nonexistent", memory_dir="/tmp")
    assert "Unknown memory backend" in str(exc_info.value)


def test_custom_backend_can_register(tmp_path):
    class _DummyBackend:
        def __init__(self, memory_dir):
            self.memory_dir = memory_dir

        def ensure_tree(self):
            pass

        def get_root_index(self):
            return ""

        def save(self, name, category, content):
            return ""

        def list_category(self, category):
            return []

        def read_leaf(self, category, filename):
            return ""

        def delete(self, category, filename):
            return False

    register_memory_backend("dummy", _DummyBackend)
    backend = get_memory_backend("dummy", memory_dir=tmp_path)
    assert isinstance(backend, _DummyBackend)
