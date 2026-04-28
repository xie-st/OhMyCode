# OhMyCode Development Guide

This document is the development reference for the OhMyCode project, for both AI agents and human developers adding features.

## Project layout

```
ohmycode/
├── __main__.py          # CLI entry
├── cli.py               # REPL + single-shot mode, rich rendering
├── core/
│   ├── messages.py      # Message types + streaming event dataclasses
│   ├── loop.py          # Main conversation loop (async generator)
│   ├── context.py       # Context management + four-level compression
│   ├── permissions.py   # Permissions pipeline (rules + mode checks)
│   ├── system_prompt.py # System prompt assembly
│   └── file_utils.py    # Shared read_lines_numbered() for file_ref + ReadTool
├── providers/
│   ├── base.py          # Provider protocol + registry
│   ├── openai.py        # OpenAI-compatible provider
│   └── anthropic.py     # Anthropic Claude provider
├── tools/
│   ├── base.py          # Tool base + registry + concurrent partitioning
│   ├── bash.py          # Shell execution
│   ├── read.py          # File read
│   ├── edit.py          # Exact string replace
│   ├── write.py         # Create / overwrite files
│   ├── glob_tool.py     # Filename globbing
│   ├── grep.py          # Regex search in files
│   ├── web_fetch.py     # HTTP fetch
│   ├── web_search.py    # Web search
│   └── agent.py         # Sub-agent
├── memory/
│   └── memory.py        # Memory system (MEMORY.md index)
├── context/
│   ├── store.py         # JSONL event log + SQLite derived context indexes
│   ├── runtime.py       # REPL-owned routing, packet cache, background tasks
│   ├── projection.py    # Topic transcript projection into virtual messages
│   ├── compression.py   # Lazy topic-level compression cache
│   └── curator.py       # Async curator for topics, packets, slices
├── storage/
│   └── conversation.py  # Conversation persistence + resume
└── config/
    └── config.py        # Four-layer config merge
```

## Module dependencies

```
cli.py → core/loop.py → providers/base.py
                       → tools/base.py → core/permissions.py
                       → tools/*.py → core/file_utils.py
                       → core/context.py
                       → core/system_prompt.py → memory/memory.py
         core/file_ref.py → core/file_utils.py
config/config.py (standalone, read everywhere)
storage/conversation.py (standalone, used from cli.py)
```

**Key constraint:** `core/permissions.py` must not import `tools/base.py` (no circular imports). Permission checks use tool name strings, not the `Tool` class.

## Extension points

### 1. Adding a tool

Create a new file under `ohmycode/tools/`, subclass `Tool`, and decorate with `@register_tool`:

```python
from ohmycode.tools.base import Tool, ToolContext, ToolResult, register_tool

@register_tool
class MyTool(Tool):
    name = "my_tool"
    description = "Description for the LLM"
    parameters = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
        },
        "required": ["param1"],
    }
    concurrent_safe = True  # True = may run in parallel with other tools

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        # implementation
        return ToolResult(output="result text", is_error=False)
```

Tool modules are pulled in by `auto_import_tools()`; no other code changes needed.

### 2. Adding a provider

Create a new file under `ohmycode/providers/` implementing the `Provider` protocol:

```python
from ohmycode.providers.base import register_provider

class MyProvider:
    name = "my_provider"

    def __init__(self, api_key="", **kwargs):
        ...

    async def stream(self, messages, tools, system, model, **kwargs):
        # yield TextChunk / ToolCallStart / TurnComplete events
        ...

register_provider("my_provider", MyProvider)
```

Provider modules are pulled in by `auto_import_providers()`.

### 3. Configuration

Four layers merge (later wins):

```
System defaults < ~/.ohmycode/config.json < .ohmycode/config.json < CLI flags
```

### 4. Permission rules

Add entries to the `rules` array in config:

```json
{
  "tool": "tool_name",
  "match_field": "parameter_field",
  "pattern": "match_pattern",
  "match_type": "glob | regex",
  "action": "allow | deny | ask"
}
```

## Code style

- **File size:** < 500 lines per file
- **Function size:** < 50 lines per function
- **Typing:** public functions must have type annotations
- **Imports:** stdlib → third party → project
- **Async first:** tools and providers use async/await
- **Errors:** tools return `ToolResult(is_error=True)` instead of raising

## Testing

- Mirror source layout: `tests/tools/test_*.py`, `tests/core/test_*.py`
- pytest + pytest-asyncio
- Mark async tests with `@pytest.mark.asyncio`
- Shared fixtures in `tests/conftest.py`
- Run: `python3 -m pytest tests/ -v`

## Local CLI setup (required before development)

Always bind the CLI to the current workspace (avoid stale editable links):

```bash
./scripts/setup-cli.sh
pip3 show ohmycode | rg "Editable project location"
```

If the editable location is not the current repo path, reinstall from this repo directory.

CLI-only rule for this repository: always start with `ohmycode`.

If `ohmycode` is still not found, add your user script directory to PATH (macOS default):

```bash
echo 'export PATH="$HOME/Library/Python/3.9/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
which ohmycode
```

The setup script also creates a stable shim at `~/.local/bin/ohmycode` to reduce PATH drift across environments.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

feat(tools): add TimeTool
fix(providers): fix empty delta in OpenAI streaming parser
docs: update DEVELOPMENT_GUIDE
test(core): add permission rule matching tests
refactor(cli): extract render_stream helper
```

Types: `feat` | `fix` | `docs` | `test` | `refactor` | `chore`

Infer scope from paths: `ohmycode/tools/*` → `tools`, `ohmycode/core/*` → `core`, `ohmycode/providers/*` → `providers`

## Workflow for new features

1. Read this guide; understand architecture and constraints
2. Decide which module owns the feature (or add a new one)
3. Design interfaces and interactions with existing code
4. TDD: tests → fail → implement → pass
5. Keep the full suite green
6. Commit using the conventions above
