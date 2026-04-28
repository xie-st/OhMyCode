"""prompt_toolkit session factory: SlashCompleter, toolbar, prompt, keybindings."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Callable

from ohmycode.config.config import OhMyCodeConfig
from ohmycode.core.file_ref import get_at_completions
from ohmycode.core.loop import ConversationLoop
from ohmycode.skills.loader import SkillInfo

ACCENT = "#ff6b9d"
REPL_PROMPT_LINE_PREFIX = "❯  "


def _repl_prompt_prefix_display_width() -> int:
    try:
        from wcwidth import wcswidth
        w = wcswidth(REPL_PROMPT_LINE_PREFIX)
        if w >= 0:
            return w
    except ImportError:
        pass
    return len(REPL_PROMPT_LINE_PREFIX)


def _patch_pt_completion_menu_align_left(pt_session: Any) -> None:
    try:
        from prompt_toolkit.layout import walk
        from prompt_toolkit.layout.containers import FloatContainer
        from prompt_toolkit.layout.menus import CompletionsMenu, MultiColumnCompletionsMenu
    except ImportError:
        return
    left = max(0, _repl_prompt_prefix_display_width() - 1)
    for container in walk(pt_session.layout.container):
        if not isinstance(container, FloatContainer):
            continue
        for fl in container.floats:
            if isinstance(fl.content, (CompletionsMenu, MultiColumnCompletionsMenu)):
                fl.left = left
                fl.xcursor = False


def _truncate(text: str, max_len: int = 50) -> str:
    return text[:max_len - 1] + "…" if len(text) > max_len else text


def build_prompt_session(
    skills: dict[str, SkillInfo],
    conv: ConversationLoop,
    config: OhMyCodeConfig,
    get_current_mode: Callable[[], str],
) -> tuple[Any, Callable]:
    """Build a prompt_toolkit PromptSession.

    Returns (pt_session, _get_prompt_fn). Raises ImportError if prompt_toolkit
    is not installed — caller should catch and fall back to plain input().
    """
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.formatted_text import FormattedText, HTML
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style as PTStyle

    class SlashCompleter(Completer):
        _BUILTIN = {
            "/exit": "Quit",
            "/quit": "Quit (alias for /exit)",
            "/clear": "Clear conversation",
            "/new": "Save current conversation and start fresh",
            "/mode": "Switch mode (default|auto|plan)",
            "/status": "Show context and session status",
            "/context": "Show or adjust long-term context",
            "/memory": "Manage memories",
            "/vchange": "Version switch (-1 back / 1 forward)",
            "/skills": "List all skills",
            "/think": "Set reasoning effort: low | medium | high | off",
        }

        def __init__(self, skills: dict[str, SkillInfo]) -> None:
            self._skills = skills

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor

            at_pos = text.rfind("@")
            if at_pos != -1 and " " not in text[at_pos:]:
                after_at = text[at_pos + 1:]
                for full_path, meta in get_at_completions(after_at, os.getcwd()):
                    yield Completion(
                        full_path,
                        start_position=-len(after_at),
                        display=HTML(f"<b>@{full_path}</b>"),
                        display_meta=meta,
                    )
                return

            if not text.startswith("/"):
                return
            offset = len(text)
            for cmd, desc in self._BUILTIN.items():
                if cmd.startswith(text):
                    yield Completion(
                        cmd, start_position=-offset,
                        display=HTML(f"<b>{cmd}</b>"),
                        display_meta=desc,
                    )
            for skill_name, info in sorted(skills.items()):
                full = f"/{skill_name}"
                if full.startswith(text):
                    yield Completion(
                        full, start_position=-offset,
                        display=HTML(f"<ansicyan>{full}</ansicyan>"),
                        display_meta=_truncate(info.description),
                    )

    pt_style = PTStyle.from_dict({
        "completion-menu": "noinherit",
        "completion-menu.completion": "noinherit fg:#bbbbbb",
        "completion-menu.completion.current": f"noinherit noreverse fg:{ACCENT} bold",
        "completion-menu.meta.completion": "noinherit fg:#666666",
        "completion-menu.meta.completion.current": f"noinherit noreverse fg:{ACCENT}",
        "scrollbar.background": "noinherit",
        "scrollbar.button": "noinherit",
        "prompt": "fg:#888888",
        "separator": "fg:#444444",
        "bottom-toolbar": "bg:default fg:default noreverse",
        "bottom-toolbar.text": "noreverse",
        "mode-indicator": f"fg:{ACCENT} bold",
        "mode-text": "fg:#888888",
        "tool-count": "fg:#00d4aa",
        "hint": "fg:#555555",
    })

    _term_width = shutil.get_terminal_size().columns

    def _get_toolbar():
        mode_label = get_current_mode()
        tool_total = len(skills)
        status = conv.get_status_snapshot()
        context_label = f"{status['usage_percent']:.1f}% ctx"
        parts = [
            ("class:mode-indicator", "  ▸▸ "),
            ("class:mode-text", f"{mode_label} mode"),
            ("class:hint", " · "),
            ("class:tool-count", context_label),
            ("class:hint", " · "),
            ("class:tool-count", f"{tool_total}"),
            ("class:mode-text", f" skill{'s' if tool_total != 1 else ''}"),
            ("class:hint", " · "),
            ("class:hint", "↓ to complete"),
        ]
        return FormattedText(parts)

    def _get_prompt():
        sep = "─" * _term_width
        return FormattedText([
            ("class:separator", sep + "\n"),
            ("", REPL_PROMPT_LINE_PREFIX),
        ])

    def _should_complete_while_typing(buf_text: str) -> bool:
        if buf_text.startswith("/") and " " not in buf_text:
            return True
        at_pos = buf_text.rfind("@")
        return at_pos != -1 and " " not in buf_text[at_pos:]

    history_dir = Path.home() / ".ohmycode"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = str(history_dir / "history")

    _completer = SlashCompleter(skills)
    _kb = KeyBindings()

    @_kb.add("enter")
    def _handle_enter(event):
        buf = event.current_buffer
        cs = buf.complete_state
        if cs and cs.completions:
            buf.apply_completion(cs.current_completion or cs.completions[0])
        else:
            buf.validate_and_handle()

    pt_session = PromptSession(
        history=FileHistory(history_path),
        completer=_completer,
        style=pt_style,
        complete_while_typing=Condition(
            lambda: _should_complete_while_typing(
                pt_session.app.current_buffer.text
            )
        ),
        key_bindings=_kb,
        bottom_toolbar=_get_toolbar,
        prompt_continuation="   ",
    )
    _patch_pt_completion_menu_align_left(pt_session)

    return pt_session, _get_prompt
