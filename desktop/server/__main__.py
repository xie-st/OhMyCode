"""Launcher that locks in WindowsProactorEventLoopPolicy before uvicorn touches asyncio.

Why: ``ohmycode/tools/bash.py`` uses ``asyncio.create_subprocess_shell``,
which raises ``NotImplementedError`` under ``SelectorEventLoop``. uvicorn
imports ``asyncio`` (and creates the default loop) before it imports the
application module, so setting the policy inside ``main.py`` is too late —
``loop=_WindowsSelectorEventLoop`` was still observed at runtime.

This module sets the policy **first**, then imports uvicorn, so every
event loop uvicorn creates afterwards (including the one ``--reload``
spawns in the worker subprocess) is a Proactor loop on Windows.

Usage:

    python -m desktop.server

is equivalent to:

    python -m uvicorn desktop.server.main:app --port 8765 --reload

but without the bash-on-Windows breakage.
"""

from __future__ import annotations

import asyncio
import sys


def _ensure_proactor_policy() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


_ensure_proactor_policy()


def main() -> None:
    import uvicorn

    # reload=False intentional: uvicorn's --reload spawns a worker subprocess
    # which doesn't inherit the WindowsProactorEventLoopPolicy set above, so
    # the worker comes up with a SelectorEventLoop and bash tool fails with
    # NotImplementedError. Disabling reload keeps everything in one process
    # where the policy actually sticks. Restart manually after code edits.
    uvicorn.run(
        "desktop.server.main:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )


if __name__ == "__main__":
    main()
