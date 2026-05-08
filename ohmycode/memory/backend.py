"""Memory backend protocol + registry.

The kernel only needs the methods declared on ``MemoryBackend``. Concrete
implementations (e.g. ``BTreeMemoryStore``) live in their own modules and
register themselves with ``register_memory_backend``.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import pkgutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable


# ── Project memory dir resolution (used by every backend) ────────────────────


def _sanitize_slug(path_str: str) -> str:
    return hashlib.sha256(path_str.encode()).hexdigest()[:16]


def _find_git_root(cwd: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def get_project_memory_dir(cwd: str) -> str:
    """Return per-project memory directory path. Uses git root if available."""
    root = _find_git_root(cwd) or os.path.abspath(cwd)
    slug = _sanitize_slug(root)
    return str(Path.home() / ".ohmycode" / "projects" / slug / "memory")


# ── Protocol ────────────────────────────────────────────────────────────────


@runtime_checkable
class MemoryBackend(Protocol):
    """Surface the kernel and the memory tool actually call.

    A backend may implement more, but only these methods are part of the
    plug-in contract.
    """

    def ensure_tree(self) -> None: ...
    def get_root_index(self) -> str: ...
    def save(self, name: str, category: str, content: str) -> str: ...
    def list_category(self, category: str) -> list[dict]: ...
    def read_leaf(self, category: str, filename: str) -> str: ...
    def delete(self, category: str, filename: str) -> bool: ...


# ── Registry + factory ──────────────────────────────────────────────────────


_BACKEND_REGISTRY: dict[str, Callable[..., MemoryBackend]] = {}


def register_memory_backend(name: str, factory: Callable[..., MemoryBackend]) -> None:
    """Register a backend factory (typically the class itself)."""
    _BACKEND_REGISTRY[name] = factory


def get_memory_backend(name: str, **kwargs: Any) -> MemoryBackend:
    if name not in _BACKEND_REGISTRY:
        raise ValueError(
            f"Unknown memory backend: '{name}'. "
            f"Available: {list(_BACKEND_REGISTRY.keys())}"
        )
    return _BACKEND_REGISTRY[name](**kwargs)


def auto_import_memory_backends() -> None:
    """Import every sibling module so registrations happen as a side-effect."""
    package_dir = Path(__file__).parent
    skip = {"backend", "memory", "extraction", "__init__"}
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name in skip:
            continue
        importlib.import_module(f"ohmycode.memory.{module_info.name}")
