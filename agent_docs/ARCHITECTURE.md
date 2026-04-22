# OhMyCode Architecture

## Overview

OhMyCode is a minimal AI coding-assistant CLI that reproduces Claude Code's core behavior in roughly 3,000 lines of Python.

## Module dependency graph

```
cli.py → core/loop.py → providers/base.py → providers/openai.py
                       → providers/anthropic.py
                       → tools/base.py → tools/*.py
                       → core/permissions.py
                       → core/context.py
                       → core/system_prompt.py → memory/memory.py
         core/file_ref.py (leaf module, invoked from cli.py)
         skills/loader.py (leaf module, invoked from cli.py)
         storage/conversation.py (leaf module, invoked from cli.py)
         config/config.py (standalone, read by all modules)
```

**Key constraint:** `core/permissions.py` must not import `tools/base.py`, to avoid circular dependencies.

## Data flow

```
User input → cli.py
  → file_ref.expand_file_refs()  [@path tokens replaced with file contents]
  → ConversationLoop.add_user_message()
  → ConversationLoop.run_turn()  [async generator]
    → context.maybe_compress()   [if near token limit]
    → provider.stream()          [call LLM API, streaming]
      ← yield TextChunk          [text fragment]
      ← yield ToolCallStart      [tool call request]
    → permissions.check_permission()  [permission check]
    → tools.run_tool_calls()     [partitioned concurrent tool execution]
      ← yield ToolCallResult     [tool results]
    → append ToolResultMessage to messages
    → continue loop (model sees tool results and may reply again)
  ← yield TurnComplete           [turn finished]
← cli.py render_stream() renders to terminal
```

## Core modules

| Module | File | Role |
|--------|------|------|
| CLI | `cli.py` | REPL / single-shot mode, rich rendering, prompt_toolkit completion, spinner |
| File reference | `core/file_ref.py` | `@path` expansion and Tab completion candidates |
| Conversation loop | `core/loop.py` | Async-generator-driven multi-turn chat |
| Messages | `core/messages.py` | Message types and streaming-event dataclasses |
| Permissions | `core/permissions.py` | Four-stage checks (rules → mode → auto-approve → confirm) |
| Context | `core/context.py` | Token counting + four-level compression (snip / micro_compact / collapse / auto_compact) |
| System prompt | `core/system_prompt.py` | Assembles system prompt (role + CLAUDE.md + memory + environment + tools) |
| Provider | `providers/base.py` | Provider protocol + registry |
| Tools | `tools/base.py` | Tool base class + registry + concurrent partitioning |
| Memory | `memory/memory.py` | MEMORY.md index + LLM extraction |
| Persistence | `storage/conversation.py` | JSON serialization + `--resume` |
| Skills | `skills/loader.py` | Scan four-tier paths, parse frontmatter, load content |
| Config | `config/config.py` | Four-layer merge (defaults < user < project < CLI) |

## Extension points

1. **New tool** — new file under `ohmycode/tools/` + `@register_tool`
2. **New provider** — new file under `ohmycode/providers/` + `register_provider()`
3. **New skill** — `.claude/skills/<name>/SKILL.md` or `.claude/skills/<group>/<name>/SKILL.md` (same for `.ohmycode/skills/`, `.agents/skills/`)
4. **Permission rules** — `rules` array in `config.json`
5. **System prompt** — `CLAUDE.md` or `OHMYCODE.md` at project root, or `config.system_prompt_append`
