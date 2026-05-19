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
- **Window B throttling stack** — `_b_lock` + 60s cooldown + 10min/5x cap + typing-mute. v3 removed delayed tool-execution, repeated-error, long-wait, and plan-drafted automatic triggers.
- **CORE_CONCEPTS** — 9 mastery-tracked concepts in `desktop/server/profile.py`
- **小柚** — Window B persona, locked in `desktop/server/growth_prompt.py`. A full coding agent with the same tool surface as Window A, but the prompt frames its job as *coaching*, not task execution. It can run on `user_input`, `turn_complete`, and explicit user `@B` turns, then decides whether to speak.
- **`[silent]` sentinel** — when 小柚 decides the current turn has nothing worth saying, it outputs the single literal `[silent]` token (case-insensitive, surrounding whitespace allowed) as the *entire* turn. The server checks this at `TurnComplete`, suppresses the message, and pushes a `b_silent` event so the front-end spinner closes without rendering anything.
- **询问式展开** — Window B never volunteers a long explanation. Its default turn output is a *short identification* of an angle worth thinking about, followed by an *ask*: "I noticed X — want to talk through it?" Only after the user says yes (via `@B`) does B actually expand. Both microview (why / pattern / transfer for the current task) and macroview (AI-era growth: what AI takes vs what humans should learn) are surfaced this way — no asymmetry between them. B fires on three triggers: `user_input` (the moment the user sends a message to A, *before* A finishes thinking — fills the wait), `turn_complete` (after A's turn), and `user_explicit` (`@B`). See `docs/adr/0001-window-b-coach-agent.md`.
- **concept_dispositions** — per-concept user preference (`learn` / `delegate` / `skip`) stored on `UserProfile`. Soft hint to 小柚, not a hard rule; B can break ranks for a key insight but must justify it.

## Current state

- 12 commits on `feat/desktop-mvp` (M1.1 → M4.2 complete)
- 392 tests passing, zero kernel modifications
- Demo-quality fixes (B model fallback, UI Claude-Code style) in progress
- Monorepo refactor (`packages/{core,cli,desktop}`) planned for a follow-up PR
