"""Built-in system-prompt sections.

Each function returns the rendered section text (or ``None`` to skip).
``order`` weights are spaced by 10 so users can wedge a custom section in
between two built-ins without shifting everyone else.
"""

from __future__ import annotations

import os
import platform

from ohmycode.core.permissions import MODE_AUTO, MODE_DEFAULT, MODE_PLAN
from ohmycode.core.sections.registry import SectionContext, section
from ohmycode.tools.base import TOOL_REGISTRY

_MODE_DESCRIPTIONS = {
    MODE_DEFAULT: (
        "You are in DEFAULT mode. Dangerous operations (file writes, "
        "shell commands) will ask the user for confirmation."
    ),
    MODE_AUTO: (
        "You are in AUTO mode. All tool calls are executed without user "
        "confirmation."
    ),
    MODE_PLAN: (
        "You are in PLAN mode (read-only). You can read files and search, "
        "but CANNOT write files, edit, or execute commands."
    ),
}


@section("role", order=10)
def _role(ctx: SectionContext) -> str:
    return (
        "You are OhMyCode, an AI coding assistant running in the user's terminal. "
        "You help with software engineering tasks: writing code, debugging, refactoring, "
        "and explaining code. You have access to tools to read/write files, execute commands, "
        "and search the codebase. Be concise and direct."
    )


@section("project_instructions", order=20)
def _project_instructions(ctx: SectionContext) -> str | None:
    if not ctx.project_instructions:
        return None
    return f"# Project Instructions\n{ctx.project_instructions}"


@section("memory", order=30)
def _memory(ctx: SectionContext) -> str | None:
    if not ctx.memory_content:
        return None

    lines: list[str] = ["# Memory"]
    lines.append(
        "The index below lists what you remember about this user and project "
        "from prior sessions. Each entry name hints at content stored on disk; "
        "the index itself is intentionally terse to save tokens."
    )
    lines.append(ctx.memory_content.rstrip())

    has_entries = "(no memories yet)" not in ctx.memory_content
    if has_entries and ctx.memory_dir:
        lines.append(
            "Full entries live under:\n"
            f"  {ctx.memory_dir}/<category>/<filename>.md\n"
            "Category is one of: user, feedback, project, reference. "
            "Filenames are listed in each category's _SUMMARY.md. "
            "Use the read tool to open an entry when its name looks relevant."
        )
        lines.append(
            "When to consult memory (do this before answering, not after):\n"
            "- The user references prior work, decisions, or 'what we discussed'.\n"
            "- An index entry name plausibly matches the current task — open it.\n"
            "- The user states a preference or correction that may already be recorded.\n"
            "- You're about to make a judgment call (style, tooling, scope) where "
            "  past feedback would change the answer.\n"
            "Skip memory for trivial questions or when the index is clearly unrelated. "
            "Don't announce that you're checking — just check, then act."
        )
    return "\n\n".join(lines)


@section("environment", order=40)
def _environment(ctx: SectionContext) -> str:
    return (
        "# Environment\n"
        f"- Working directory: {ctx.cwd}\n"
        f"- Platform: {platform.system()} {platform.release()}\n"
        f"- Shell: {os.environ.get('SHELL', 'unknown')}\n"
        f"- Python: {platform.python_version()}"
    )


@section("mode", order=50)
def _mode(ctx: SectionContext) -> str:
    description = _MODE_DESCRIPTIONS.get(ctx.mode, _MODE_DESCRIPTIONS[MODE_DEFAULT])
    return f"# Mode\n{description}"


@section("tools", order=60)
def _tools(ctx: SectionContext) -> str | None:
    if not TOOL_REGISTRY:
        return None
    lines = ["# Available Tools"]
    for name, tool_cls in sorted(TOOL_REGISTRY.items()):
        tool = tool_cls()
        lines.append(f"- **{name}**: {tool.description}")
    return "\n".join(lines)


@section("append", order=70)
def _append(ctx: SectionContext) -> str | None:
    return ctx.system_prompt_append or None
