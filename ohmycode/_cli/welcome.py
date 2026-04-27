"""REPL welcome banner: ASCII block letters + meta rows."""

from __future__ import annotations

from rich.text import Text

from ohmycode._cli.output import ACCENT


_OHMY_BLOCK_LINES = (
    " ██████╗██╗  ██╗███╗   ███╗██╗   ██╗\n"
    "██╔═══██╗██║  ██║████╗ ████║╚██╗ ██╔╝\n"
    "██║   ██║███████║██╔████╔██║ ╚████╔╝ \n"
    "██║   ██║██╔══██║██║╚██╔╝██║  ╚██╔╝  \n"
    "╚██████╔╝██║  ██║██║ ╚═╝ ██║   ██║   \n"
    " ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝   ╚═╝   "
)


def build_repl_welcome_text(model_display: str, mode: str, n_skills: int) -> Text:
    """Big block letters + subtitle + aligned meta rows."""
    t = Text()
    t.append(_OHMY_BLOCK_LINES, style=ACCENT)
    t.append("  ")
    t.append("Code", style=f"bold {ACCENT}")
    t.append(" v0.1.0\n\n", style="dim")
    label_w = 12
    t.append("Model".ljust(label_w), style="dim")
    t.append(f"{model_display}\n", style="bold")
    t.append("Mode".ljust(label_w), style="dim")
    t.append(f"{mode}\n", style="green")
    t.append("Skills".ljust(label_w), style="dim")
    t.append(f"{n_skills} available\n", style="dim")
    return t
