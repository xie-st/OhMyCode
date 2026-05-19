# Domain Docs

Single-context layout:

- `CONTEXT.md` at repo root — project language, key concepts, current state
- `docs/adr/` — Architectural Decision Records (`NNNN-short-title.md`)

## Skill consumers

- `improve-codebase-architecture` — reads `CONTEXT.md` to know domain vocabulary; reads ADRs to avoid re-litigating past decisions
- `diagnose` — uses `CONTEXT.md` to understand what "normal" behavior means
- `tdd` — checks ADRs before proposing tests that contradict prior decisions
- `grill-with-docs` — sharpens terminology against `CONTEXT.md` and updates ADRs inline

## Status

Both placeholders right now:

- `CONTEXT.md` is a stub at repo root — run `improve-codebase-architecture` skill to draft real content, or fill manually
- `docs/adr/` is empty except `.gitkeep` — add ADRs as architectural decisions get made

## ADR naming

`docs/adr/NNNN-short-title.md`, e.g.:
- `0001-window-b-uses-same-model-as-window-a.md`
- `0002-desktop-window-b-trigger-throttling-stack.md`

Keep ADRs short (1-2 pages) and immutable (mark superseded ones with a header pointing at the new one).
