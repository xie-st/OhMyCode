"""Pluggable system-prompt sections.

``build_system_prompt`` calls ``assemble_sections(ctx, names=...)`` which
walks the registry in ``order`` ascending and stitches together every
non-empty result.

To add a section: write a function returning ``str | None`` (None means
"skip me"), then register it via ``@section("my_name", order=55)``.
Built-in sections live in ``builtin.py`` and register themselves on
import.
"""

from __future__ import annotations

from ohmycode.core.sections.registry import (
    SectionContext,
    SectionProvider,
    assemble_sections,
    auto_import_sections,
    register_section,
    section,
)

__all__ = [
    "SectionContext",
    "SectionProvider",
    "assemble_sections",
    "auto_import_sections",
    "register_section",
    "section",
]
