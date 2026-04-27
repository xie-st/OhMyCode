"""System prompt builder — assembles the system message from multiple sources."""
from __future__ import annotations
import os
import platform
from pathlib import Path
from ohmycode.core.permissions import MODE_AUTO, MODE_DEFAULT, MODE_PLAN
from ohmycode.tools.base import TOOL_REGISTRY

def _build_memory_section(memory_content: str, memory_dir: str) -> str:
    """Compose the # Memory section.

    The index alone tells the model what exists; this section also tells it
    where the full entries live, when to expand them, and how. Without that,
    the index reads as decoration and gets ignored.
    """
    lines: list[str] = ["# Memory"]
    lines.append(
        "The index below lists what you remember about this user and project "
        "from prior sessions. Each entry name hints at content stored on disk; "
        "the index itself is intentionally terse to save tokens."
    )
    lines.append(memory_content.rstrip())

    has_entries = "(no memories yet)" not in memory_content
    if has_entries and memory_dir:
        lines.append(
            "Full entries live under:\n"
            f"  {memory_dir}/<category>/<filename>.md\n"
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


def build_system_prompt(mode: str, cwd: str, memory_content: str = "",
    memory_dir: str = "", project_instructions: str = "",
    system_prompt_append: str = "") -> str:
    parts: list[str] = []
    parts.append(
        "You are OhMyCode, an AI coding assistant running in the user's terminal. "
        "You help with software engineering tasks: writing code, debugging, refactoring, "
        "and explaining code. You have access to tools to read/write files, execute commands, "
        "and search the codebase. Be concise and direct."
    )
    if project_instructions:
        parts.append(f"# Project Instructions\n{project_instructions}")
    if memory_content:
        parts.append(_build_memory_section(memory_content, memory_dir))
    env_info = (f"# Environment\n- Working directory: {cwd}\n"
        f"- Platform: {platform.system()} {platform.release()}\n"
        f"- Shell: {os.environ.get('SHELL', 'unknown')}\n"
        f"- Python: {platform.python_version()}")
    parts.append(env_info)
    mode_descriptions = {
        MODE_DEFAULT: "You are in DEFAULT mode. Dangerous operations (file writes, shell commands) will ask the user for confirmation.",
        MODE_AUTO: "You are in AUTO mode. All tool calls are executed without user confirmation.",
        MODE_PLAN: "You are in PLAN mode (read-only). You can read files and search, but CANNOT write files, edit, or execute commands.",
    }
    parts.append(f"# Mode\n{mode_descriptions.get(mode, mode_descriptions[MODE_DEFAULT])}")
    if TOOL_REGISTRY:
        tool_lines = ["# Available Tools"]
        for name, tool_cls in sorted(TOOL_REGISTRY.items()):
            tool = tool_cls()
            tool_lines.append(f"- **{name}**: {tool.description}")
        parts.append("\n".join(tool_lines))
    if system_prompt_append:
        parts.append(system_prompt_append)
    return "\n\n".join(parts)

def find_project_instructions(start_dir: str) -> str:
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
