# Core module interfaces

## core/file_utils.py

Shared file reading utility used by both `core/file_ref.py` and `tools/read.py`.

```python
# Read a file and return (numbered_text, is_truncated).
# offset: 1-indexed first line; limit: max lines (None = all).
# max_bytes / max_lines: hard caps (None = no cap).
# Raises OSError / FileNotFoundError / PermissionError on I/O failure.
read_lines_numbered(
    path: Path,
    offset: int = 1,
    limit: int | None = None,
    max_bytes: int | None = None,
    max_lines: int | None = None,
) -> tuple[str, bool]
```

Line number format: `{line_number}\t{line_content}` (1-indexed, tab-separated).

## core/file_ref.py

Handles `@path` file reference expansion and Tab completion candidates. Invoked by `cli.py` before passing user input to `ConversationLoop`. Uses `core/file_utils.read_lines_numbered()` with `max_bytes=100_000, max_lines=2_000`.

```python
# Expand all @path tokens in a message to <file>...</file> blocks.
# Returns (expanded_text, warnings). Never raises.
# Files > 100 KB or > 2000 lines are truncated with a notice.
# Missing files: @path is left unchanged; a warning is appended.
expand_file_refs(text: str, cwd: str) -> tuple[str, list[str]]

# Return up to 50 (path_string, meta_label) pairs for Tab completion after @.
# prefix: text already typed after @, e.g. "" or "src/" or "src/mai"
# Skips dotfiles. Directories are suffixed with "/"; files show size in KB.
get_at_completions(prefix: str, cwd: str) -> list[tuple[str, str]]
```

Injection format (Anthropic-recommended XML tags):
```
<file path="src/main.py">
1	#!/usr/bin/env python3
2	...
</file>
```

## tools/base.py

```python
@dataclass
class ToolContext:
    mode: str           # "default" | "auto" | "plan"
    agent_depth: int    # 0 = top level
    cwd: str
    is_sub_agent: bool

@dataclass
class ToolResult:
    output: str
    is_error: bool

class Tool(ABC):
    name: str
    description: str
    parameters: dict        # JSON Schema
    concurrent_safe: bool   # True = may run in parallel

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult: ...

# Registration
@register_tool
class MyTool(Tool): ...

# Execution
run_tool_calls(calls, ctx) -> dict[str, ToolResult]  # partitioned concurrency
```

## providers/base.py

```python
class Provider(Protocol):
    name: str
    async def stream(self, messages, tools, system, model, **kwargs) -> AsyncIterator[StreamEvent]: ...

# Register
register_provider("name", MyProvider)

# Resolve
get_provider("name", api_key=...) -> Provider
```

`Provider.stream()` must yield events in this order:

1. `TextChunk(text=...)` — zero or more text fragments
2. `ToolCallStart(tool_name=..., tool_use_id=..., params=...)` — zero or more tool calls
3. `TurnComplete(finish_reason=..., usage=...)` — **must be last**

## core/loop.py

`ConversationLoop.get_status_snapshot()` exposes current REPL/session status for `/status`, including message count, approximate used tokens, effective context window, usage percent, and the compression stage (`ok` | `snip` | `micro_compact` | `collapse` | `auto_compact`).

## core/messages.py

Message types: `UserMessage`, `AssistantMessage`, `ToolResultMessage`, `SystemMessage`  
Event types: `TextChunk`, `ToolCallStart`, `ToolCallResult`, `TurnComplete`, `TokenUsage`

All messages implement `to_api_dict()` for the API payload.

## core/permissions.py

```python
check_permission(tool_name, params, mode, rules, auto_approved) -> PermissionResult
# PermissionResult.action: "allow" | "deny" | "ask"
```

Dangerous tools: `bash`, `edit`, `write`, `agent`  
Blocked in plan mode: `bash`, `edit`, `write`, `agent`

## skills/loader.py

```python
scan_skills(cwd=".") -> dict[str, SkillInfo]  # scan four-tier paths
load_skill(skill, arguments="") -> str         # load body, replace $ARGUMENTS
parse_frontmatter(text) -> (dict, str)         # split YAML frontmatter from body
```

Search order (highest priority first): `.ohmycode/skills/` > `.claude/skills/` > `.agents/skills/` > `~/.ohmycode/skills/`

Under each root: either `<skill>/SKILL.md` or one nested level `<group>/<skill>/SKILL.md` (e.g. `superpowers/brainstorming`); registry keys use the inner folder name `<skill>`.

## config/config.py

```python
load_config(cli_overrides) -> OhMyCodeConfig
merge_configs(base, override) -> dict  # scalars overridden, arrays concatenated, objects deep-merged
```
