# OhMyCode Architecture

## Overview

OhMyCode is a minimal AI coding-assistant CLI that reproduces Claude Code's core behavior in roughly 3,000 lines of Python.

## Module dependency graph

```
cli.py → _cli/output.py        [ScrollingBox, ThinkingBox, MemoryBox, SubAgentBox, render_stream]
       → _cli/prompt_session.py [SlashCompleter, build_prompt_session]
       → _cli/repl_commands.py  [handle_slash_command and per-command fns]
       → core/loop.py → providers/base.py → providers/openai.py
                       → providers/anthropic.py
                       → tools/base.py → tools/*.py → core/file_utils.py
                       → core/permissions.py
                       → core/context.py
                       → core/system_prompt.py → memory/memory.py
         core/file_ref.py (leaf module, invoked from cli.py) → core/file_utils.py
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
  → _stream_with_cancel()        [asyncio.Task wrapper; races render vs cancel_event]
    → ConversationLoop.run_turn()  [async generator]
        → context.maybe_compress()   [if near token limit]
        → provider.stream()          [call LLM API, streaming]
          ← yield TextChunk          [text fragment]
          ← yield ToolCallStreaming   [tool call detected, params still streaming]
          ← yield ToolCallStart      [tool call fully parsed, ready to execute]
        → permissions.check_permission()  [permission check]
        → tools.run_tool_calls()     [partitioned concurrent tool execution]
          ← yield ToolCallResult     [tool results]
        → append ToolResultMessage to messages
        → continue loop (model sees tool results and may reply again)
      ← yield TurnComplete           [finish_reason: "stop"|"tool_use"|"cancelled"|"max_turns"]
    ← cli.py render_stream() renders to terminal
  [Ctrl+C] → signal handler sets threading.Event
           → _stream_with_cancel cancels Task → CancelledError propagates into run_turn()
           → run_turn() saves partial AssistantMessage + fills placeholder ToolResultMessages
           → yields TurnComplete(finish_reason="cancelled"), re-raises CancelledError
```

## Core modules

| Module | File | Role |
|--------|------|------|
| CLI entry | `cli.py` | Argument parsing + dispatch only; Windows ANSI guard at module top |
| Single-shot mode | `_cli/single_shot.py` | `run_single()` — one prompt then exit |
| REPL mode | `_cli/repl.py` | `run_repl()` + `_stream_with_cancel` (Ctrl+C handling) |
| Welcome banner | `_cli/welcome.py` | ASCII block banner + meta rows |
| Tool confirmation | `_cli/confirm.py` | `confirm_tool_call()` y/n/a prompt |
| `vchange` subcommand | `commands/vchange.py` | git-based version switch |
| Stream rendering | `_cli/output.py` | `ScrollingBox` base + `ThinkingBox` / `MemoryBox` / `SubAgentBox` panels, `render_stream` async consumer, spinner |
| Prompt session | `_cli/prompt_session.py` | `SlashCompleter`, prompt_toolkit session factory (Enter selects, not submits) |
| REPL commands | `_cli/repl_commands.py` | `/exit` `/clear` `/new` `/mode` `/status` `/memory` `/think` `/skills` + skill dispatch |
| File reference | `core/file_ref.py` | `@path` expansion and Tab completion candidates |
| File utilities | `core/file_utils.py` | Shared `read_lines_numbered()` used by `file_ref` and `ReadTool` |
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

## Long-term Context Curator

The REPL owns long-term context state through `ohmycode/context/runtime.py`. `ConversationLoop` still owns only short-term messages, provider streaming, compression, and tool execution.

Normal REPL turns now add this pre/post layer:

1. Expanded user input is appended to a daily JSONL event shard as `user_message`.
2. `ContextRuntime.prepare_for_turn()` routes the message to an active topic and reuses or updates the cached `ContextPacket`.
3. `_cli/context_flow.py` builds a topic transcript projection: same-topic turns keep the current `ConversationLoop.messages`; topic switches replace them with that topic's reconstructed virtual messages.
4. `render_stream()` passes the projection system prompt to `ConversationLoop.run_turn()`.
5. After the turn, assistant/tool/turn events are appended to the event log.
6. A coalesced background `ContextCurator` task updates topic summaries, packet fields, and topic slices; lazy topic compression may then cache `compressed history + raw tail`.

Long-term source events live under `~/.ohmycode/projects/<project_slug>/context/events/YYYY-MM-DD.jsonl`. `context.db` stores indexes and derived state: topics, packets, topic slices, compression cache, and curator state. `/new` clears only short-term `ConversationLoop.messages` when context is enabled; `/mode` creates a fresh loop for the mode but keeps the same REPL-owned context runtime.
