# Core module interfaces

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
# Core module interfaces

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
# Core module interfaces

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
