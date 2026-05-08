"""System-prompt assembly.

The actual section content lives under ``ohmycode.core.sections``; this
module exists for backwards compatibility and to host
``find_project_instructions``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ohmycode.core.sections import (
    SectionContext,
    assemble_sections,
    auto_import_sections,
)


def build_system_prompt(
    mode: str,
    cwd: str,
    memory_content: str = "",
    memory_dir: str = "",
    project_instructions: str = "",
    system_prompt_append: str = "",
    sections: Iterable[str] | None = None,
) -> str:
    """Assemble the system prompt from the registered sections.

    ``sections=None`` uses every registered section in default order.
    Pass an iterable of names to restrict to a subset (in registry order,
    not the order of the iterable — order is the section's job).
    """
    auto_import_sections()
    ctx = SectionContext(
        mode=mode,
        cwd=cwd,
        memory_content=memory_content,
        memory_dir=memory_dir,
        project_instructions=project_instructions,
        system_prompt_append=system_prompt_append,
    )
    return assemble_sections(ctx, names=sections)


def find_project_instructions(start_dir: str) -> str:
    """Walk up to 10 ancestors looking for CLAUDE.md or OHMYCODE.md."""
    current = Path(start_dir).resolve()
    for _ in range(10):
        for name in ("CLAUDE.md", "OHMYCODE.md"):
            candidate = current / name
            if candidate.is_file():
                try:
                    return candidate.read_text(encoding="utf-8")
                except OSError:
                    return ""
        parent = current.parent
        if parent == current:
            break
        current = parent
    return ""
