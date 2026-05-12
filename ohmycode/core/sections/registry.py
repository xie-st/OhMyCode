"""``SectionContext`` + ``SectionProvider`` + section registry."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable


@dataclass
class SectionContext:
    """Everything a section might need to render itself."""

    mode: str
    cwd: str
    project_instructions: str = ""
    memory_content: str = ""
    memory_dir: str = ""
    system_prompt_append: str = ""


@runtime_checkable
class SectionProvider(Protocol):
    name: str
    order: int

    def render(self, ctx: SectionContext) -> str | None: ...


_REGISTRY: dict[str, SectionProvider] = {}


def register_section(provider: SectionProvider) -> SectionProvider:
    """Register a section provider; returns it so it can be used as a decorator helper."""
    _REGISTRY[provider.name] = provider
    return provider


def section(
    name: str, order: int
) -> Callable[[Callable[[SectionContext], str | None]], Callable[[SectionContext], str | None]]:
    """Decorator: turn a ``ctx -> str | None`` function into a registered section."""

    def _decorate(
        fn: Callable[[SectionContext], str | None]
    ) -> Callable[[SectionContext], str | None]:
        class _FunctionalSection:
            def __init__(self) -> None:
                self.name = name
                self.order = order

            def render(self, ctx: SectionContext) -> str | None:
                return fn(ctx)

        register_section(_FunctionalSection())
        return fn

    return _decorate


def assemble_sections(
    ctx: SectionContext, names: Iterable[str] | None = None
) -> str:
    """Render every selected section in ``order`` ascending; join with blank lines.

    ``names=None`` means "use every registered section". Names not in the
    registry are silently skipped — that way disabling a section is a
    one-liner in config without raising on stale entries.
    """
    if names is None:
        selected = list(_REGISTRY.values())
    else:
        selected = [_REGISTRY[n] for n in names if n in _REGISTRY]

    selected.sort(key=lambda p: p.order)
    parts: list[str] = []
    for provider in selected:
        rendered = provider.render(ctx)
        if rendered:
            parts.append(rendered)
    return "\n\n".join(parts)


def auto_import_sections() -> None:
    """Import every sibling so registrations happen as a side effect."""
    package_dir = Path(__file__).parent
    skip = {"registry", "__init__"}
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name in skip:
            continue
        importlib.import_module(f"ohmycode.core.sections.{module_info.name}")
