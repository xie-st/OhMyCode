# Gotchas

## 1. Do not `await` `provider.stream()`

`provider.stream()` is an async generator (`async def` + `yield`), not a coroutine.

- Wrong: `async for event in await provider.stream(...)`
- Right: `async for event in provider.stream(...)`

## 2. `rich.Live` conflicts with prompt_toolkit

`rich.Live` uses terminal cursor control for in-place updates and fights `prompt_toolkit`, causing repeated redraws when the terminal scrolls.

- Fix: use `sys.stdout.write` + ANSI escapes (`\r\033[K`) for the spinner

## 3. `permissions.py` must not import `tools/base.py`

That creates a circular import. Permission checks match tool names as strings and do not depend on the `Tool` class.

## 4. tiktoken is inaccurate for Claude models

Expect ~5–15% error. Compression thresholds are conservative (triggers ~10% earlier than the nominal ratio).

## 5. `TOOL_REGISTRY` stores classes, not instances

`register_tool` stores `type[Tool]`; execution does `tool_cls()`. They are not `Tool` instances.

## 6. OpenAI streams tool `arguments` in chunks

Arguments arrive as multiple `delta.tool_calls[idx].function.arguments` fragments. Accumulate by index, then `json.loads` the full string.

## 7. Azure OpenAI needs `AsyncAzureOpenAI`

Do not use plain `AsyncOpenAI` + `base_url`; use `AsyncAzureOpenAI(azure_endpoint=..., api_version=...)`.

## 8. Completion menu background: `bg:default`

Fixed colors (e.g. `bg:#1a1a2e`) look wrong across themes. `bg:default` blends with the terminal background.

## 9. Skill mascot "eyes" use spaces

The mascot's eyes are spaces showing the terminal background, not `on <color>` fills. `on <color>` paints solid blocks and hides the "eyes."

## 10. REPL: raw `console.print` between prompts breaks IME

Rich output between `prompt_toolkit` prompts moves the terminal cursor without updating PT's renderer; macOS Chinese/Japanese IME often stops working after long multi-line output (e.g. `/skills`).

- Fix: wrap prints in `prompt_toolkit.patch_stdout.patch_stdout()` (`_repl_print` in `cli.py`).

## 12. Ctrl+C during streaming cannot be caught with `except KeyboardInterrupt` on Windows

On Windows (ProactorEventLoop), pressing Ctrl+C while awaiting a network call causes asyncio to cancel the underlying Future, raising `asyncio.CancelledError` from deep inside the httpx/anyio stack. This exception propagates up through all user coroutines and is caught by `asyncio.run()`, which re-raises it as `KeyboardInterrupt` **outside** the user coroutine stack — any `except KeyboardInterrupt` in `render_stream()` or `run_turn()` never fires.

Fix: register `signal.signal(SIGINT, ...)` before `asyncio.run()` to intercept the signal and set a `threading.Event`. Wrap `render_stream()` in an `asyncio.Task` and use `asyncio.wait()` to race it against the cancel event. On cancel, call `task.cancel()` to inject a controlled `CancelledError` inside the Task boundary, which `run_turn()` can catch and handle gracefully.

Side-effect: any `AssistantMessage` with `tool_calls` that was written to history before the interrupt must have corresponding `ToolResultMessage` entries, or the next API call returns 400. `run_turn()` fills in placeholder `ToolResultMessage("Cancelled by user.")` for every unanswered tool call.

## 11. Anthropic thinking: adaptive vs manual, and max_tokens

When `reasoning_effort` is set, the Anthropic provider must choose between two API modes:
- **Claude 4 models** (`claude-opus-4`, `claude-sonnet-4`, `claude-haiku-4`): use `thinking: {type: "adaptive", effort: "..."}`. Sending `type: "enabled"` on these models returns a 400 error.
- **Older models** (claude-3-7-sonnet etc.): use `thinking: {type: "enabled", budget_tokens: N}`.

Also, enabling thinking requires `max_tokens` to be large enough (≥ 16000); the default 4096 causes an API error.

## 12. ThinkingChunk event passthrough requires explicit handling in loop.py

`run_turn()` uses explicit `isinstance` branches to decide what to do with each provider event. Unknown event types are **silently dropped** — they do not pass through automatically. When adding a new event type (e.g. `ThinkingChunk`), you must add a corresponding `elif isinstance(event, ThinkingChunk): yield event` branch in `run_turn()`, otherwise it never reaches the CLI.

The `thinking_delta` content block delta from the Anthropic SDK uses `delta.thinking` (not `delta.text`) as the attribute name. The block type is identified via `delta.type == "thinking_delta"` in the `content_block_delta` event handler.
