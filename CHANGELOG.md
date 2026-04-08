# Changelog

All notable changes to OhMyCode are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `/quit` as alias for `/exit` — both commands now save the conversation and extract memories before quitting

### Fixed
- Resume: `--resume` now overwrites the original conversation file on `/exit` instead of creating a new one each time
- Resume: `--resume` (no argument) now picks the most recently *saved* session by file modification time, rather than by filename lexicographic order — so resuming, chatting, and exiting always lands back on the right file next time
- Resume: "Resumed conversation from" message now correctly shows the save timestamp (`saved_at`) instead of displaying "unknown"

## [0.1.0] — 2026-04-07

### Added
- Initial release: REPL, streaming output, tool execution, permission modes, context compression, memory system, conversation resume, skills, and benchmarking suite
- 9 built-in tools: `bash`, `read`, `edit`, `write`, `glob`, `grep`, `web_fetch`, `web_search`, `agent`
- Provider support: OpenAI, Anthropic, Azure, and OpenAI-compatible APIs
- Built-in skills: `add-tool`, `add-provider`, `add-feature`, `customize-system-prompt`, `customize-response-style`, `commit-conventions`, `debug-ohmycode`, `gen-tests`, `run-tests`, `bench`

### Fixed
- ANSI colors restored correctly when printing inside `patch_stdout` on Windows
- `SetConsoleMode` guarded and prompt_toolkit console cached to prevent errors on Windows
