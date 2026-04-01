<div align="center">
  <h1>🐙 OhMyCode</h1>
  <p><b>~3000 lines of Python. That's the entire thing.</b><br>
  A fully-functional CC-style AI coding assistant you can read in an afternoon — and tell it to extend itself.</p>
  <p>
    <img src="https://img.shields.io/badge/python-≥3.9-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/lines-~3000-orange" alt="Lines">
    <img src="https://img.shields.io/badge/tools-9-cyan" alt="Tools">
    <img src="https://img.shields.io/badge/tests-72-brightgreen" alt="Tests">
  </p>
</div>

## Why OhMyCode?

**It's tiny.** OhMyCode delivers the CC-style coding assistant experience — streaming, tool use, context compression, memory — in ~3000 lines you fully own.

**It extends itself.** Say "add a tool that does X" and it modifies its own source to build one. No plugin SDK, no API boundaries.

## Highlights

- **Self-Extending** — Ask the AI to add tools, providers, or skills; it modifies its own code to grow
- **9 Built-in Tools** — Bash, Read, Edit, Write, Glob, Grep, WebFetch, WebSearch, Agent
- **Multi-Provider** — OpenAI, Anthropic, Azure, or any OpenAI-compatible API
- **Permission Pipeline** — `default` / `auto` / `plan` modes with rule-based control
- **Smart Context** — Four-level compression keeps long conversations running
- **Memory & Resume** — LLM-based memory extraction + `--resume` to pick up where you left off
- **Skill System** — `SKILL.md` files guide the AI on specific tasks; autocomplete via `/skill-name`
- **CC-Style UI** — Thinking spinner, tool panels, permission prompts, rich rendering

## Install

```bash
git clone <repo-url>
cd OhMyCode
pip install -e ".[dev]"
```

> [!TIP]
> If `ohmycode` is not found, use `python3 -m ohmycode` or add pip's script directory to your PATH.

## Quick Start

```bash
ohmycode                        # interactive REPL
ohmycode -p "Fix the bug"      # single-shot prompt
ohmycode --resume               # resume last conversation
ohmycode --mode plan            # read-only mode
```

### REPL Commands

| Command | Description |
|---------|------------|
| `/exit` | Quit (auto-saves + extracts memories) |
| `/clear` | Clear history |
| `/mode <mode>` | Switch mode (`default` / `auto` / `plan`) |
| `/memory list\|delete` | Manage memories |
| `/skills` | List skills |
| `/<skill-name>` | Run a skill |

## Configuration

Create `~/.ohmycode/config.json`:

```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "api_key": "sk-...",
  "mode": "auto"
}
```

Config merges four layers: **system defaults** < **user** (`~/.ohmycode/`) < **project** (`.ohmycode/`) < **CLI args**.

CLI overrides: `--provider`, `--model`, `--mode`, `--api-key`, `--base-url`.

<details>
<summary>All config options</summary>

| Key | Default | Description |
|-----|---------|-------------|
| `provider` | `"openai"` | LLM provider |
| `model` | `"gpt-4o"` | Model name |
| `mode` | `"default"` | Permission mode |
| `base_url` | `""` | API base URL |
| `api_key` | `""` | API key |
| `azure_endpoint` | `""` | Azure endpoint |
| `azure_api_version` | `"2024-02-01"` | Azure API version |
| `max_turns` | `100` | Max conversation turns |
| `token_budget` | `200000` | Token budget |
| `output_tokens_reserved` | `8192` | Reserved output tokens |
| `rules` | `[]` | Permission rules |
| `system_prompt_append` | `""` | Appended to system prompt |
| `search_api` / `search_api_key` | `""` | Web search API config |

</details>

## Built-in Tools

| Tool | Safe | Description |
|------|:----:|------------|
| `bash` | ✗ | Shell commands with timeout |
| `read` | ✓ | Read files with line range |
| `edit` | ✗ | Find-and-replace (unique match) |
| `write` | ✗ | Create/overwrite files |
| `glob` | ✓ | Find files by pattern |
| `grep` | ✓ | Regex search across files |
| `web_fetch` | ✓ | Fetch URL → text |
| `web_search` | ✓ | DuckDuckGo search |
| `agent` | ✗ | Sub-agent (max depth 2) |

> **Safe** = runs in parallel via `asyncio.gather()`. Mixed batches: safe first, then unsafe.

## Extending (or: Let It Extend Itself)

The fastest way to add a feature? **Ask OhMyCode to do it.** It can read its own source, write new files, and run tests — so "add a tool that counts words" is a single prompt away.

You can also do it manually:

- **Add a tool** — create `ohmycode/tools/my_tool.py`, auto-discovered. See `/add-tool` skill.
- **Add a provider** — create `ohmycode/providers/my_provider.py`, auto-discovered. See `/add-provider` skill.
- **Add a skill** — create `SKILL.md` in `.ohmycode/skills/`, `.claude/skills/`, `.agents/skills/`, or `~/.ohmycode/skills/` (searched in that order).

## Project Structure

```
ohmycode/
├── cli.py               # REPL + rendering
├── core/
│   ├── loop.py          # Conversation loop
│   ├── messages.py      # Message types + streaming events
│   ├── context.py       # Token counting + compression
│   ├── permissions.py   # Permission pipeline
│   └── system_prompt.py # System prompt assembly
├── providers/           # OpenAI, Anthropic (auto-discovered)
├── tools/               # 9 built-in tools (auto-discovered)
├── skills/loader.py     # Skill scanner
├── memory/memory.py     # MEMORY.md + LLM extraction
├── storage/conversation.py  # JSON persistence + resume
└── config/config.py     # Four-layer config merge
```

## Testing

```bash
python3 -m pytest tests/ -v   # 72 tests
```

## License

MIT
