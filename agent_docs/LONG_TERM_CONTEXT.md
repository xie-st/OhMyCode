# OhMyCode Long-Term Context Architecture

This document describes the "infinite-window with background-agent context management" system that OhMyCode uses to support arbitrarily long conversations without hitting the model's token budget.

It is also written so that **another AI assistant** (with no prior exposure to this codebase) can read it and understand the design well enough to extend or port it. The second half of the file is a self-contained briefing prompt for that purpose.

---

## Part 1 — How it works (for humans)

### 1.1 The problem

A single chat session can run for hours and accumulate millions of tokens of history. Two naive solutions both fail:

- **Truncate** (sliding window): the model forgets what it decided 30 turns ago.
- **Keep everything**: token cost grows linearly, and eventually the model hits its hard window limit.

OhMyCode's answer: **don't store the conversation as one linear log at all**. Treat the history as an append-only event stream, organize events into *topics*, and run a background LLM as a **curator** that continuously rewrites a short *packet* of structured working context for each topic. Only the packet (plus a small tail of recent raw events) is ever shown to the foreground model.

### 1.2 The four moving parts

```
┌──────────────────────────────────────────────────────────────────────┐
│  FOREGROUND (sync, runs on every user message — must be fast)        │
│                                                                       │
│  user input → expand @file refs → record event → route to topic      │
│            → load packet → build projection → inject as system msg   │
│            → run_turn() → record assistant/tool/turn events          │
│            → schedule background curator                             │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ event_id watermark
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  BACKGROUND (async, coalesced — at most one running)                 │
│                                                                       │
│  curator agent  →  read events after last_processed_event_id         │
│                 →  ask curator LLM: keep/patch/rebuild/new_topic     │
│                 →  apply patch to ContextPacket + topic slices       │
│                 →  advance last_processed_event_id                   │
│                                                                       │
│  topic compressor (post-curator) → if topic raw history is large,    │
│                                    LLM-compress into messages_json   │
│                                    cached at a watermark             │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PERSISTENCE                                                          │
│  ~/.ohmycode/projects/<slug>/context/                                │
│    ├── events/YYYY-MM-DD.jsonl    (append-only, source of truth)     │
│    └── context.db                  (SQLite: indexes + derived state) │
└──────────────────────────────────────────────────────────────────────┘
```

The four layers:

| Layer | File | What it owns |
|---|---|---|
| **Runtime** | [ohmycode/context/runtime.py](../ohmycode/context/runtime.py) | Per-REPL coordinator. Records events, routes to topics, builds packets, schedules background work. |
| **Store** | [ohmycode/context/store.py](../ohmycode/context/store.py) | Persistence. JSONL shards + SQLite. The JSONL is the source of truth; SQLite is index + derived state. |
| **Curator** | [ohmycode/context/curator.py](../ohmycode/context/curator.py) | Background LLM agent that summarizes events into a `ContextPacket`. |
| **Projection** | [ohmycode/context/projection.py](../ohmycode/context/projection.py) | Builds the per-turn message window from cached compressed history + raw tail. |

The REPL glue lives in [ohmycode/_cli/context_flow.py](../ohmycode/_cli/context_flow.py) and [ohmycode/_cli/repl.py](../ohmycode/_cli/repl.py).

### 1.3 Data model

**`ContextEvent`** ([store.py:17](../ohmycode/context/store.py#L17)) — the atomic unit. Append-only. Six event types:

| Type | Recorded when |
|---|---|
| `user_message` | User submits input (post @file expansion) |
| `assistant_message` | Model reply finishes streaming |
| `tool_call` | Model issues a tool invocation |
| `tool_result` | A tool execution returns |
| `turn_complete` | A turn ends with a `finish_reason` |
| `context_correction` | User explicitly fixes routing via `/context switch` / `/context rebuild` |

Each event has: `id` (global sequential), `event_type`, `content` (the canonical model-facing payload), `metadata` (audit data — raw input, image hashes, tool params, ref warnings), `created_at` (ISO timestamp).

**`Topic`** ([store.py:27](../ohmycode/context/store.py#L27)) — a coherent unit of work (e.g. "fix auth flow", "refactor DB layer"). Fields: `id`, `title`, `summary`, `status`, `data`, `updated_at`.

**`TopicSlice`** ([store.py:36](../ohmycode/context/store.py#L36)) — a range `(topic_id, start_event_id, end_event_id)` marking which events belong to a topic. A topic can have many non-contiguous slices.

**`ContextPacket`** ([packet.py:9](../ohmycode/context/packet.py#L9)) — the structured working context for one topic, rendered into the system prompt on every turn. Fields:

```python
topic_id, title, summary, status,
decisions: list[str],         # decisions already made
open_questions: list[str],    # unresolved issues
next_actions: list[str],      # planned next steps
related_files: list[str],     # file paths involved
related_topics: list[str],    # cross-topic links
global_memory: list[str],     # MEMORY.md cross-references
version: int,                 # bumped when semantic content changes
last_event_id: int            # watermark: events processed into this packet
```

`packet.render(max_chars=24_000)` produces a markdown block titled `# Current Working Context` that is appended to the base system prompt on every long-term-context turn.

**`TopicCompressionCache`** ([store.py:44](../ohmycode/context/store.py#L44)) — pre-computed LLM-compressed history for one topic, with a watermark (`compressed_until_event_id`) and the serialized `Message` list (`messages_json`). Avoids re-running the compression LLM on every turn.

### 1.4 Per-turn synchronous flow

This runs every time the user hits Enter. Code path: [_cli/repl.py:320-354](../ohmycode/_cli/repl.py).

1. **Expand `@file` refs**: `expand_file_refs(user_input, cwd)` returns `(expanded_input, image_blocks, ref_warnings)`.
2. **Record `user_message`**: `runtime.record_user_message(expanded_input, raw_content=..., image_blocks=..., ref_warnings=...)` → appends event, returns `user_event_id`.
3. **Topic routing + packet load**: `runtime.prepare_for_turn(user_text, base_system_prompt, last_event_id=user_event_id)` (runtime.py:107) returns a `PreparedContext` containing:
   - `route: RouteDecision` (action ∈ `{patch, switch, keep, ambiguous, new_topic}`)
   - `packet: ContextPacket` for the chosen topic
   - `system_prompt`: `base_system_prompt + "\n\n" + packet.render()`
4. **Build projection**: `apply_context_projection(conv, runtime, prepared, base_system_prompt)` ([context_flow.py:10](../ohmycode/_cli/context_flow.py#L10)) calls `build_topic_projection` which:
   - Loads the topic's compression cache (if any) → `compressed history` as a list of `Message`
   - Loads raw events in this topic's slices after the watermark → `raw tail`
   - Concatenates them
   - **Replaces `conv.messages` with the projection** if the route was `switch / new_topic / rebuild`, OR if a compression cache exists. Otherwise leaves `conv.messages` alone (same-topic continuation).
5. **Add user message to loop**: `conv.add_user_message(expanded_input, image_blocks=...)`.
6. **Run turn**: `_stream_with_cancel(conv, system_prompt_override, allow_blocking_compression=False)`. The override is the projection's prompt (base + packet). `allow_blocking_compression=False` skips the foreground LLM-based compression — the background curator/compressor will handle it instead.
7. **Record post-turn events**: walk the new messages produced this turn and emit `assistant_message`, `tool_call`, `tool_result`, `turn_complete` events.
8. **Schedule background curator**: `_schedule_context_curator()` ([repl.py:157](../ohmycode/_cli/repl.py#L157)) creates a `ContextCurator` and calls `runtime.request_curator_run(...)` which coalesces (one task at a time, with a pending flag).

### 1.5 Topic routing (heuristic, multilingual)

`ContextRuntime._route()` decides which topic the message belongs to. **It is a heuristic, not LLM-based** — must be fast (synchronous, runs on every turn).

Scoring ([runtime.py:`_score`](../ohmycode/context/runtime.py)):
- Extract features from user text via `_features()`: lowercase Latin tokens (alphanumeric, stopwords filtered) + **CJK n-grams** (full sequence ≤4 chars, otherwise bigrams + trigrams) over Chinese (U+3400–U+9FFF), Hiragana, Katakana, and Hangul ranges.
- For each candidate topic, score = `overlap(query, title) × 3 + overlap(query, summary) × 2 + overlap(query, packet_text) × 1`.
- Pick the highest. Ties → `action="ambiguous"`; low confidence and an existing active topic → `action="keep"`.

Decisions: `"new_topic"` (no topics), `"patch"` (same as active), `"switch"` (better-scoring topic exists), `"keep"` (low confidence; stay put), `"ambiguous"` (top 2 tied; curator will sort it out asynchronously).

### 1.6 Background curator agent

The curator is itself an LLM call, run after each foreground turn. Coalesced: only one runs at a time; new events arriving during a run set `_curator_pending=True` and trigger one more pass when the current one finishes.

**Input to curator** (`build_provider_curate_fn` in [curator.py](../ohmycode/context/curator.py)):
```json
{
  "events": [
    {"id": 42, "type": "user_message", "content": "...", "metadata": {...}, "created_at": "..."},
    ...
  ],
  "topics": [
    {"id": "topic_auth", "title": "fix auth flow", "summary": "...", "status": "..."}
  ]
}
```
Only events with `id > last_processed_event_id` are sent. The system prompt is the verbatim `CURATOR_SYSTEM` constant ([curator.py:18-23](../ohmycode/context/curator.py#L18)).

**Output schema** (the curator must return this JSON):
```json
{
  "action": "keep|patch|rebuild|new_topic",
  "topic": {"id": "", "title": "", "summary": "", "status": ""},
  "packet_patch": {
    "summary": "",
    "decisions": [],
    "open_questions": [],
    "next_actions": [],
    "related_files": [],
    "related_topics": [],
    "global_memory": []
  },
  "topic_slices_mode": "merge|replace",
  "topic_slices": [
    {"topic_id": "", "start_event_id": 1, "end_event_id": 2}
  ]
}
```

Apply logic (`ContextCurator._apply`):
- Update the topic row (`title/summary/status`) if provided.
- Load the packet (create one if missing for a new topic). Merge each list field from `packet_patch` — only increment `packet.version` if a field actually changed.
- Set `packet.last_event_id = processed_event_id`. Save packet.
- Apply `topic_slices`: `mode == "replace"` overwrites the topic's slice set; `"merge"` (default) unions new ranges with existing ones.
- Advance `last_processed_event_id` to the highest event id in this batch.

**Self-heal** ([curator.py:41-59](../ohmycode/context/curator.py#L41)): if `last_processed_event_id > max_event_id` (e.g. JSONL truncated externally, project-slug collision, manual DB edit), the curator resets to 0 and reprocesses from scratch. Logged at `WARNING`.

### 1.7 Topic compression layer

[ohmycode/context/compression.py](../ohmycode/context/compression.py). Runs **after** the curator, only for the topic the curator just updated.

Algorithm:
1. Load all raw events in this topic's slices.
2. If the topic's projected message count would push the model over `threshold` (default 80%) of its budget, run LLM-based auto-compaction.
3. Persist the compressed `Message` list as `TopicCompressionCache(topic_id, compressed_until_event_id=max(event.id), messages_json=..., summary=...)`.

On the next turn, projection prefers the cache: read cache → append raw events with id > `compressed_until_event_id`.

### 1.8 Persistence layout

```
~/.ohmycode/projects/<project_slug>/context/
├── events/
│   ├── 2026-05-10.jsonl    # one JSON object per line; source of truth
│   ├── 2026-05-11.jsonl
│   └── 2026-05-12.jsonl
└── context.db              # SQLite: indexes + derived state
```

`project_slug` is derived from the git root path (normalized, lowercased on Windows) via `get_project_memory_dir(cwd)`. Two different working directories that resolve to the same git root share a context.

SQLite tables ([store.py](../ohmycode/context/store.py)):
- `event_index(event_id, shard, created_at)` — points to which JSONL shard contains each event.
- `events` — legacy mirror, backfilled from `event_index + JSONL` on store open. Kept for older code paths.
- `topics`, `topic_events`, `context_packets`, `topic_slices`, `topic_compression_cache` — derived state.
- `curator_state` — key-value store: `last_processed_event_id`, `next_event_id`, `active_topic_id`, etc.

The JSONL is **never rewritten**. All "compression" happens in derived caches.

### 1.9 Healthy-projection checklist

When debugging, verify each:

1. **`Working directory`** in the injected context matches the intended project root. Starting `ohmycode` from a parent directory attaches to that parent's slug, NOT a child repo automatically.
2. **`Active topic`** describes the current task, not an old one.
3. **Packet fields** (`summary`, `decisions`, `open_questions`, `next_actions`, `related_files`) reference the current work.
4. **`Transcript Projection`** includes slices from the active topic; `raw_tail_event_count` matches recent same-topic turns.

Repair commands: `/context topics` (list), `/context switch <topic_id>`, `/context rebuild`.

### 1.10 Known failure modes

- **Project-slug collision**: two paths normalize to the same slug → contexts merge.
- **Parent-vs-child cwd**: launching from a parent dir → parent's context, not the inner repo's.
- **Curator lag**: if foreground events outpace the curator, the packet shown is stale until it catches up. Visible as `Curator lag: N` in `/context`.
- **Malformed curator JSON**: `json.JSONDecodeError` is caught; the turn still succeeds, but the packet isn't updated. Logged.
- **Slice boundary at tool_call/tool_result**: a slice can end at an `assistant_message` containing a tool_call while the matching `tool_result` is just outside. Projection extends through adjacent tool events ([projection.py:125-144](../ohmycode/context/projection.py)) and inserts a placeholder if data is incomplete, so the model never sees a tool_call without a result.
- **`/new` vs. long-term context**: with context enabled, `/new` clears only `conv.messages` and `auto_approved` — it does NOT delete events, topics, or packets. To reset the long-term state, use `/context rebuild`.

---

## Part 2 — Briefing prompt for another AI

Copy everything between the lines below into the other assistant's input. It is written to be self-contained: no need for the reader to have seen this codebase or this document.

---

```
You are about to read code or work on a system called "OhMyCode" (a minimal Claude Code clone in Python). Before you start, here is everything you need to know about its long-term context / "infinite window" architecture. This is a self-contained briefing — do not assume any prior exposure.

# Problem this system solves

Chat history grows without bound. Truncating loses information; keeping everything blows the token budget. OhMyCode never sends the raw history to the foreground model. Instead it:

1. Stores every interaction as an append-only event log on disk.
2. Groups events into "topics" using a fast heuristic router.
3. Runs a background LLM ("curator") that incrementally summarizes events into a structured "context packet" per topic.
4. On every foreground turn, injects only that packet (plus a small tail of recent raw events) into the system prompt.

The foreground model sees a window scoped to one topic, with old history pre-summarized. The user perceives an infinite session.

# Two execution paths

**Foreground (synchronous, runs on every user message — must be fast, no LLM calls except the main reply):**

```
user input
  → expand @file references in input
  → append a `user_message` event to the log
  → route the message to a topic (heuristic; details below)
  → load that topic's ContextPacket from disk
  → build a "projection": (compressed_history_messages + raw_tail_messages)
  → if the route is switch/new_topic/rebuild OR a compression cache exists,
    REPLACE conv.messages with the projection
  → inject `base_system_prompt + packet.render()` as the system prompt
  → run the main LLM turn
  → after turn: append assistant_message, tool_call, tool_result, turn_complete events
  → schedule the background curator (coalesced: at most one running)
```

**Background (asynchronous, coalesced):**

```
curator agent (LLM call):
  → read all events with id > last_processed_event_id
  → read the current list of topics
  → send both as JSON to a curator LLM with a strict response schema
  → apply the response: update topic metadata, merge a packet patch,
    add/replace topic slices (event-id ranges)
  → advance last_processed_event_id

topic compressor (runs after curator if the active topic was updated):
  → if the topic's raw message history would push usage over a threshold,
    LLM-compress it into a list of Message objects
  → cache it with a watermark (compressed_until_event_id)
```

# Data model

A **ContextEvent** is the atomic unit. Append-only. Six types: `user_message`, `assistant_message`, `tool_call`, `tool_result`, `turn_complete`, `context_correction`. Each has: `id` (global sequential int), `event_type`, `content` (model-facing payload), `metadata` (audit data, never re-shown to the model), `created_at` (ISO timestamp).

A **Topic** is a coherent unit of work. Fields: `id`, `title`, `summary`, `status`. Topics are created by the curator.

A **TopicSlice** is a tuple `(topic_id, start_event_id, end_event_id)`. A topic can own many non-contiguous slices. The curator sets these.

A **ContextPacket** is the structured working context for ONE topic. This is the only thing the foreground model sees about long-term history. Fields:

  topic_id, title, summary, status,
  decisions:       list[str]   # decisions already made
  open_questions:  list[str]   # unresolved issues
  next_actions:    list[str]   # planned next steps
  related_files:   list[str]   # file paths involved
  related_topics:  list[str]   # cross-topic links
  global_memory:   list[str]   # references to a separate MEMORY.md system
  version:         int         # bumped only when semantic content changes
  last_event_id:   int         # watermark: events processed into this packet

The packet renders to markdown under a `# Current Working Context` header and is concatenated onto the base system prompt for every turn while context is enabled.

A **TopicCompressionCache** stores LLM-compressed Message lists per topic, with a watermark event id. The foreground projection step uses this cache to avoid re-summarizing on every turn.

# Persistence

```
~/.ohmycode/projects/<project_slug>/context/
├── events/YYYY-MM-DD.jsonl    # daily shards, append-only, SOURCE OF TRUTH
└── context.db                 # SQLite indexes and derived state
```

`project_slug` is derived from the git root of cwd (normalized, lowercased on Windows). Two cwds that resolve to the same git root share a context.

SQLite tables: `event_index` (event_id → shard), `events` (legacy mirror, backfilled from JSONL on open), `topics`, `topic_events`, `context_packets`, `topic_slices`, `topic_compression_cache`, `curator_state` (KV: last_processed_event_id, next_event_id, active_topic_id, ...).

**JSONL is never rewritten.** All summarization happens in derived caches in SQLite. To "rebuild" you reset `last_processed_event_id` and let the curator reprocess.

# Topic routing (heuristic, runs synchronously on every turn)

Pure scoring function, no LLM call. For each existing topic:

  score = overlap(query, title)   * 3
        + overlap(query, summary) * 2
        + overlap(query, packet_text) * 1

`overlap` is a sum-of-min count of shared "features". `features(text)` produces:
  - lowercase Latin word tokens (alphanumeric), filtered against a small stopword list
  - **CJK n-grams**: for runs of characters in the ranges
    U+3400–U+9FFF (Chinese), U+3040–U+30FF (Hiragana + Katakana), U+AC00–U+D7AF (Hangul),
    take the full sequence if length ≤4, otherwise all bigrams + trigrams

Decisions:
  - "new_topic": no topics exist
  - "patch":     best-scoring topic == current active topic
  - "switch":    a different topic scores higher with reasonable confidence
  - "keep":      low confidence; stay on the active topic
  - "ambiguous": top 2 topics tied; route gets resolved by the curator on the next async pass

The projection step REPLACES the foreground model's message window iff the route is `switch`, `new_topic`, or `rebuild`, OR a compression cache exists for the topic. Otherwise it keeps the existing window (same-topic continuation).

# Curator JSON schema (verbatim)

The curator LLM is given this system prompt:

"""
You are OhMyCode's background context curator.
Read recent append-only events and existing topic workspaces. Return compact JSON only.
Use this shape:
{"action":"keep|patch|rebuild|new_topic","topic":{"id":"","title":"","summary":"","status":""},"packet_patch":{"summary":"","decisions":[],"open_questions":[],"next_actions":[],"related_files":[],"related_topics":[],"global_memory":[]},"topic_slices_mode":"merge|replace","topic_slices":[{"topic_id":"","start_event_id":1,"end_event_id":2}]}
packet_patch list fields must be arrays of plain strings, not objects.
topic_slices marks raw event ranges owned by a topic. Default topic_slices_mode is "merge"; use "replace" only when rebuilding a topic's complete slice set. Prefer small patches. Do not include markdown.
"""

User message to the curator is a JSON object with two keys:
  events: [ {id, type, content, metadata, created_at}, ... ]   # all events after last_processed_event_id
  topics: [ {id, title, summary, status}, ... ]                 # current topic list

Application rules:
- Update topic row from `topic.{title,summary,status}` if present.
- Merge each list field in `packet_patch` into the packet. Increment `packet.version` only if the merged value differs from the previous value (not just because `last_event_id` advances).
- Set `packet.last_event_id` to the highest processed event id.
- `topic_slices_mode` = "merge" (default) unions ranges; "replace" overwrites the topic's slice set entirely.
- Always advance `last_processed_event_id`.

# Critical invariants

1. **Events are immutable.** Never modify or delete a JSONL row. To correct state, append a `context_correction` event or rebuild.
2. **The curator is coalesced.** At most one curator task runs at a time. New events during a run set a pending flag, triggering exactly one more pass after the current one finishes. Do not naively spawn a curator per turn.
3. **The projection can replace `conv.messages`.** It is not additive. The foreground loop's working window is whatever the projection step produces, scoped to one topic.
4. **Self-heal**: if `last_processed_event_id > max(events.id)` on disk (e.g., external truncation, slug collision, manual edit), the curator resets to 0 and reprocesses from scratch. Log a WARNING.
5. **Tool-call/tool-result pairs must not cross slice boundaries naively.** When a slice ends at an `assistant_message` carrying a tool_call, the projection step is responsible for extending into the matching `tool_result` event (or inserting an error placeholder) so the foreground model never sees an orphan tool_call.
6. **Don't run blocking compression in foreground when context is enabled.** Pass `allow_blocking_compression=False` to the main turn loop. The background curator + topic compressor handle long-term summarization.
7. **packet.version is the cache key for callers.** Don't bump it for cosmetic changes — only when summary/decisions/open_questions/next_actions/related_files/related_topics/global_memory actually changed.

# Foreground UX commands

- `/context`        — show active topic, packet metadata, curator lag, compression state.
- `/context topics` — list all topics with slice counts.
- `/context switch <topic_id>` — force the active topic (writes a `context_correction` event).
- `/context rebuild` — request the curator to rebuild the active topic's packet from scratch.
- `/new`            — clears the foreground `conv.messages` window. Does NOT touch events/topics/packets. The next message still routes to a topic.

# Failure modes to keep in mind

- **Slug collision**: two project paths normalize to the same slug → contexts merge unexpectedly.
- **Parent-cwd**: launching from a parent dir uses the parent's slug, not the inner repo's.
- **Curator lag**: large bursts of events leave the packet stale until the curator catches up.
- **Malformed curator JSON**: catch `JSONDecodeError`, log, leave state untouched, do not crash.

# When extending this system

- New event type? Append-only; add a producer in `runtime.py` and a renderer in `projection.py`. The curator schema doesn't need to change — events are passed through opaquely.
- New packet field? Add it to `ContextPacket`, update `packet.render()`, extend the curator system prompt's JSON shape, and add merge logic. Bump `packet.version` semantics.
- New router signal? Add it to `_features()`. Keep it CHEAP — this runs synchronously on every keystroke-submission, before the model call.
- Don't put LLM calls in the foreground path. The only synchronous LLM call per turn is the main reply.
```

---

End of briefing.
