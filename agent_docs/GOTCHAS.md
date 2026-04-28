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

## 11. Ctrl+C during streaming cannot be caught with `except KeyboardInterrupt` on Windows

On Windows (ProactorEventLoop), pressing Ctrl+C while awaiting a network call causes asyncio to cancel the underlying Future, raising `asyncio.CancelledError` from deep inside the httpx/anyio stack. This exception propagates up through all user coroutines and is caught by `asyncio.run()`, which re-raises it as `KeyboardInterrupt` **outside** the user coroutine stack — any `except KeyboardInterrupt` in `render_stream()` or `run_turn()` never fires.

Fix: register `signal.signal(SIGINT, ...)` before `asyncio.run()` to intercept the signal and set a `threading.Event`. Wrap `render_stream()` in an `asyncio.Task` and use `asyncio.wait()` to race it against the cancel event. On cancel, call `task.cancel()` to inject a controlled `CancelledError` inside the Task boundary, which `run_turn()` can catch and handle gracefully.

Side-effect: any `AssistantMessage` with `tool_calls` that was written to history before the interrupt must have corresponding `ToolResultMessage` entries, or the next API call returns 400. `run_turn()` fills in placeholder `ToolResultMessage("Cancelled by user.")` for every unanswered tool call.

## 12. `threading.Event.wait()` with no timeout blocks the executor thread forever

`asyncio.to_thread(cancel_event.wait)` starts a thread that blocks on `cancel_event.wait()` indefinitely. Cancelling the returned asyncio Task (via `task.cancel()`) only cancels the Python-level Future wrapper — it cannot interrupt the underlying thread, which keeps blocking. When `asyncio.run()` closes the event loop, it waits up to 300 seconds for all executor threads to finish before giving up, causing a visible hang on exit.

Fix: replace the bare `cancel_event.wait` with a polling wrapper that loops on `cancel_event.wait(timeout=0.1)` and exits when a separate `stop_polling` event is set. Set `stop_polling` on both exit paths (cancel fired / render finished) so the thread exits within ~100 ms.

## 13. Anthropic thinking: adaptive vs manual, and max_tokens

When `reasoning_effort` is set, the Anthropic provider must choose between two API modes:
- **Claude 4 models** (`claude-opus-4`, `claude-sonnet-4`, `claude-haiku-4`): use `thinking: {type: "adaptive", effort: "..."}`. Sending `type: "enabled"` on these models returns a 400 error.
- **Older models** (claude-3-7-sonnet etc.): use `thinking: {type: "enabled", budget_tokens: N}`.

Also, enabling thinking requires `max_tokens` to be large enough (≥ 16000); the default 4096 causes an API error.

## 15. Sub-agent inherits parent config via ToolContext

`AgentTool` creates a new `ConversationLoop` for the sub-agent. Using `OhMyCodeConfig()` (the default constructor) drops `api_key`, `model`, and `provider`, causing the sub-agent to fail with connection timeouts.

Fix: pass `config=self.config` when building the root `ToolContext` in `ConversationLoop.initialize()`. `AgentTool.execute()` then does `copy.copy(ctx.config)` and overrides only `mode`, preserving all credentials.

## 16. Multiple concurrent SubAgentBoxes clobber each other's terminal output

`AgentTool.concurrent_safe = False` keeps sub-agents serial. If it were set to `True`, two `SubAgentBox` instances running concurrently would both issue `\033[{N}A\033[J` cursor-up/erase sequences against the same `sys.stdout`, corrupting each other's display. Fix before enabling parallelism: gate all `_draw()` / `clear()` calls behind a shared `asyncio.Lock`, or render both boxes as a single combined frame.

## 17. Sub-agent progress events are buffered, not real-time

`AgentTool.execute()` does not import `_cli/*`; instead it pushes `SubAgentToolUse` and `SubAgentDone` events through `ToolContext.event_emitter`, which `core/loop.py` wires to a buffer list. The loop flushes the buffer right before yielding `ToolCallResult` for the agent call. Consequence: the `SubAgentBox` panel materializes only after the sub-agent finishes — it does not stream live tool-by-tool. This is the cost of keeping `tools/agent.py` decoupled from the renderer; lifting it would require an `asyncio.Queue` consumer task running concurrently with `run_tool_calls`.

## 14. ThinkingChunk event passthrough requires explicit handling in loop.py

`run_turn()` uses explicit `isinstance` branches to decide what to do with each provider event. Unknown event types are **silently dropped** — they do not pass through automatically. When adding a new event type (e.g. `ThinkingChunk`), you must add a corresponding `elif isinstance(event, ThinkingChunk): yield event` branch in `run_turn()`, otherwise it never reaches the CLI.

The `thinking_delta` content block delta from the Anthropic SDK uses `delta.thinking` (not `delta.text`) as the attribute name. The block type is identified via `delta.type == "thinking_delta"` in the `content_block_delta` event handler.
