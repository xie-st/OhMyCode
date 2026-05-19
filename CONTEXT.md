# OhMyCode — Project Context

> **Status**: stub. Fill in via `improve-codebase-architecture` skill or manually.
> See `docs/agents/domain.md` for how this file is consumed.

## What this project is

OhMyCode is a minimal Claude Code–style clone in roughly 3,000 lines of Python.
It supports a REPL, streaming output, tool execution, a permissions pipeline,
context compression, a memory system, and skills.

A `desktop/` wrapper (Window A + Window B "小柚" growth-agent) sits on top of
the kernel and adds a FastAPI + React desktop UI without modifying the kernel.

## Key concepts and language

(To be filled — examples that should land here when this file gets fleshed out:)

- **ConversationLoop** — kernel async generator yielding `StreamEvent`s
- **EventBus** — observer fanning kernel events to multiple subscribers (e.g. Window A renderer + Window B observer)
- **DesktopSession** — Window A + Window B + WebSocket fan-out wrapper
- **UserProfile** — per-project JSON profile (skills / concepts / gaps) under `~/.ohmycode/projects/<slug>/profile/profile.json`
- **Window B throttling stack** — `_b_lock` + 60s cooldown + 10min/5x cap + 3s tool-trigger delay + typing-mute
- **CORE_CONCEPTS** — 9 mastery-tracked concepts in `desktop/server/profile.py`
- **小柚** — Window B persona, locked in `desktop/server/growth_prompt.py`

## Current state

- 12 commits on `feat/desktop-mvp` (M1.1 → M4.2 complete)
- 392 tests passing, zero kernel modifications
- Demo-quality fixes (B model fallback, UI Claude-Code style) in progress
- Monorepo refactor (`packages/{core,cli,desktop}`) planned for a follow-up PR
