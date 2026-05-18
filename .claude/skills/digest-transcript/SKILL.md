---
name: digest-transcript
description: Batch-process a folder of video/livestream transcripts (.srt / .vtt / .md / .txt). Pipeline: normalize → topic-extract → topic-merge → write per-session digest → cross-session categorize + overview → per-category stitched reading. Output: one digest.md per session in md/parts/ (original wording with timestamps preserved), md/<category>.md (verbatim category aggregation), md/notes/<category>.md (the same content stitched into readable prose with timestamps removed), and md/总论.md (cross-session overview).
---

# digest-transcript — Batch transcript digester

> **Audience**: the **orchestrator agent** that received `/digest-transcript`. You drive the whole pipeline. The `agent` tool spawns workers; workers see only the prompt you craft — never this document. Treat `WORKER PROMPT` blocks as opaque payloads to substitute and send verbatim.

Turns long video/livestream transcripts into a topic-segmented "skim version" that preserves the original wording (just removes filler, repetition, and obvious slips). Each segment carries an anchor (timestamp for SRT/VTT, line number for plain text) so the user can jump back to the source.

## Input Contract

The user points you at a **folder**. Each supported file in that folder is one **session** (think: one livestream, one lecture).

```
<folder>/
├── 2025-05-01.srt   ← session
├── 2025-05-02.txt   ← session
├── 2025-05-03.md    ← session
└── notes.docx       ← ignored (unsupported extension)
```

Supported extensions: `.srt`, `.vtt`, `.md`, `.txt`. **Do not recurse** into subdirectories.

For each input file `<folder>/<name>.<ext>`, the **session directory** is `<folder>/<name>/` (sibling to the input). Each session directory contains two subdirectories: `subtitles/` (copy of source), `intermediate/` (temp files), and a `digest.md` at the session root (not inside an `output/` wrapper).

## Arguments — `$ARGUMENTS`

Parse `$ARGUMENTS` (space-separated, in any order):

| Token | Meaning |
|---|---|
| *(empty)* | Target folder = current working directory |
| A path that **is** a directory | Target folder |
| A path that **is** a supported file | Process only this one session |
| `stage0` / `stage1` / `stage2` / `stage3` | Run only that stage for the targeted session(s), regenerating its output unconditionally |
| `stage4` | Run only the folder-level categorization & overview, regenerating its output unconditionally. Requires every session in `<folder>` to already have `intermediate/topic_map.json` and `intermediate/topics/`. |
| `stage5` | Run only the per-category reading-notes step, regenerating its output unconditionally. Requires `<folder>/md/categories.json` (from Stage 4b) and every referenced `<session>/intermediate/topics/<topic_id>.md` to still exist. |

If no stage token is given, run the full pipeline. **Skip a session if its `<session_dir>/digest.md` already exists** (only when no stage token is given). Stage 4 and Stage 5 run at the end of the folder pass when targeting a folder; they are **not** run when the target is a single file.

## Output Layout

During processing:
```
<folder>/
├── <name>.<ext>                    # source, untouched (for glob discovery)
├── <name>/                         # one session directory per input file
│   ├── subtitles/                  # copy of original source file     [kept]
│   │   └── <name>.<ext>
│   ├── intermediate/               # all intermediate files           [* deleted by cleanup]
│   │   ├── normalized.jsonl        # Stage 0 output
│   │   ├── stage1/chunk_<N>/topics.json  # Stage 1 output
│   │   ├── topic_map.json          # Stage 2 output
│   │   └── topics/<topic_id>.md    # Stage 3 outputs
│   └── digest.md                   # topic-segmented skim version (no output/ wrapper)
```

`[*]` = deleted by the **single** cleanup step that runs **after Stage 5 finishes** (or after the last session, when the target is a single file). The per-session intermediates therefore coexist with outputs on disk throughout the run so Stage 4 and Stage 5 can read them.

The source file stays under `<folder>/<name>.<ext>` during processing for glob discovery. After all stages finish, the final folder structure is:

```
<folder>/
├── srt/                             # all source .srt files, moved here after cleanup
│   └── <name>.<ext>
├── md/                              # all deliverable markdown files
│   ├── 总论.md                      # cross-session overview (Stage 4d)
│   ├── <category-name-1>.md         # original-text category aggregations (Stage 4c)
│   ├── <category-name-2>.md
│   ├── notes/                       # per-category reading notes (Stage 5)
│   │   ├── <category-name-1>.md
│   │   └── <category-name-2>.md
│   └── parts/                       # per-session digests
│       ├── 第1部分.md
│       ├── 第2部分.md
│       └── ...
├── <name>/                          # per-session directories with subtitles/ copy
│   └── subtitles/
│       └── <name>.<ext>
```

---

## Orchestrator Procedure — Top Level

> **Windows 环境注意**: `bash` 工具执行 `type`、`python -c "..."` 等命令时，stdout 可能因编码问题截断或为空。验证文件写入是否成功时，优先使用 `dir <path>` 或 `powershell -Command "Get-Item <path>"` 做检查，不要依赖 `type` 或 `python -c "with open..."` 的 stdout 回显。`write` 工具和 Python `open()` 写入本身不受影响——只影响回显。

1. Parse `$ARGUMENTS` into `target` (folder or single file) and optional `stage`.
2. **Handle `stage4` / `stage5` as special early branches**: if `stage == "stage4"`, the target must resolve to a folder, skip everything below and go straight to *Stage 4*. If `stage == "stage5"`, the target must resolve to a folder, skip everything below and go straight to *Stage 5*.
3. Build the session list:
   - If `target` is a single file: list = `[target]`. **Stage 4 and Stage 5 will be skipped** for single-file mode.
   - Else: call `glob_tool` once per extension (`<target>/*.srt`, `<target>/*.vtt`, `<target>/*.md`, `<target>/*.txt`), union the results, sort.
4. Filter out sessions whose `<session_dir>/digest.md` already exists, **unless** a `stage` token was given.
5. If the filtered list is empty and a stage token forces nothing, print `Nothing to do.` and stop. Otherwise continue (Stage 4 and Stage 5 may still need to run on already-digested sessions).
6. Print the planned session list (one line each) before starting.
7. **Process sessions sequentially** (one fully done through Stage 3 + Final Assembly before the next starts). Within a session, Stage 1 and Stage 3 workers run in parallel. **Do not run per-session cleanup yet** — the folder-level Stage 4 and Stage 5 still need `intermediate/topic_map.json` and `intermediate/topics/`.
8. After each session finishes, print one line: `<name>: <topic count> topics, digest at <session_dir>/digest.md`.
9. **After all sessions finish**, run Stage 4 (folder mode only). If targeting a single file, skip Stage 4.
10. **After Stage 4 finishes**, run Stage 5 (folder mode only). If targeting a single file, skip Stage 5.
11. **After Stage 5 finishes** (or at the end of single-file mode), run the unified cleanup pass over every processed session. During cleanup, also move source files to `srt/` and copy deliverable md to `md/parts/`.

If a session fails (worker error, malformed input, etc.), print `<name>: FAILED — <reason>` and continue to the next session. Never let one bad file abort the whole batch. Stage 4 / Stage 5 then run over whichever sessions actually produced `intermediate/topic_map.json` and `intermediate/topics/`.

---

## Stage 0 — Normalize (orchestrator does this itself, no workers)

Deterministic string processing. No LLM needed beyond your own judgement.

1. `read` the input file in full (use `offset`/`limit` to page if it errors on size — pull in chunks and concatenate in working memory).
2. Detect format:
   - `.srt` → SRT branch
   - `.vtt` → VTT branch
   - `.md` / `.txt` → plain-text branch
3. Parse to a list of records, each shaped like:
   ```json
   {"idx": <1-based int>, "ts": "HH:MM:SS" or null, "text": "<one line of content>"}
   ```

### SRT parsing rules

An SRT cue is three+ lines separated from the next cue by a blank line:
```
<sequence number>
HH:MM:SS,mmm --> HH:MM:SS,mmm
<text line 1>
[<text line 2> ...]
```
- `idx` = sequential 1-based counter you assign (do **not** trust the file's sequence numbers — they can be wrong).
- `ts` = the start timestamp formatted as `HH:MM:SS` (drop milliseconds).
- `text` = join the cue's text lines with a single space; strip leading/trailing whitespace; strip SRT inline tags like `<i>`, `</i>`, `{\an8}`.

### VTT parsing rules

Same as SRT except:
- Skip the leading `WEBVTT` header and any `NOTE` / `STYLE` / `REGION` blocks.
- Cue identifier line is optional; cues are recognized by the `-->` timestamp line.
- Timestamp format is `HH:MM:SS.mmm` (dot, not comma). Drop milliseconds the same way.

### Plain-text parsing rules (.md / .txt)

- `ts` is always `null`.
- Split the file into records by paragraph: a paragraph is a maximal run of non-blank lines. Join its lines with a single space. Strip leading/trailing whitespace.
- For `.md`: skip pure heading lines (`^#+ `), code fences (```` ``` ```` blocks — drop them entirely), and pure horizontal rules (`---`, `***`).
- `idx` = 1-based counter across surviving paragraphs.

### Write the output

1. Copy the source file into the session directory: use the `bash` tool to run `copy "<source_file>" "<session_dir>/subtitles/<name>.<ext>"` (on Windows) or `cp "<source_file>" "<session_dir>/subtitles/<name>.<ext>"` (on Linux/macOS). Create the `subtitles/` directory first with `mkdir "<session_dir>/subtitles"`.
2. Call `write` to create `<session_dir>/intermediate/normalized.jsonl` — one JSON object per line, no trailing comma, in `idx` order.

If `<session_dir>/intermediate/normalized.jsonl` exists and no stage token forced regen, you may skip this stage for that session.

> **验证写入**: 写完文件后，用 `dir <session_dir>/intermediate/normalized.jsonl` 确认文件存在且大小不为 0 即可。不要用 `type` 或 `python -c "..."` 回显内容——管道编码问题可能导致误判写入失败。

---

## Stage 1 — Topic Extraction (parallel workers, one per chunk)

1. `read` `<session_dir>/intermediate/normalized.jsonl`. Count records.
2. Chunk by record count (rough proxy for tokens, since you don't have a tokenizer in the orchestrator): **~80 records per chunk with a 10-record overlap**. So chunks span records [1..80], [71..150], [141..220], etc. Number chunks starting at 1.
3. For each chunk, decide whether to skip: if `<session_dir>/intermediate/stage1/chunk_<N>/topics.json` exists and no stage token forced regen, skip it.
4. For each non-skipped chunk, call the `agent` tool **once in parallel** (all chunk workers in a single message with multiple tool calls). The `prompt` is `WORKER PROMPT — STAGE 1` below with **every** placeholder literally substituted. Before sending, scan the prompt and confirm zero `<...>` markers remain.
5. After all workers return, print `Stage 1: <N> chunks done` for the session.

### WORKER PROMPT — STAGE 1

> Substitute `<SESSION_DIR>`, `<CHUNK_N>`, `<START_IDX>`, `<END_IDX>` everywhere, then send as the `prompt` argument to the `agent` tool.

```
You are a single-purpose worker. Your only job is to extract topic boundaries
from one chunk of a normalized transcript. You may not use the `agent` tool.

Available tools: read, write. Do not use any others.

Input file:  <SESSION_DIR>/intermediate/normalized.jsonl
Chunk index: <CHUNK_N>
Your slice:  records with idx in [<START_IDX>, <END_IDX>] (inclusive on both ends)
Output file: <SESSION_DIR>/intermediate/stage1/chunk_<CHUNK_N>/topics.json

Steps (in order, no others):

1. `read` the input file. If it errors, your final reply must be exactly:
   "READ FAILED: <error message from read>" and you must stop.
2. Filter to the records whose `idx` is in [<START_IDX>, <END_IDX>]. Ignore
   the rest. Read them in `idx` order to understand what the speaker is
   actually talking about.
3. Identify topic boundaries within your slice. A "topic" is a contiguous
   span of records that the speaker spends discussing one coherent subject.
   Be CONSERVATIVE: a 70-record slice usually contains 1–3 topics. Do not
   split on every digression or example. If the whole slice is one topic,
   output one topic. If you cannot tell, output one topic.
4. Call `write` to create the output file as a JSON array. Each entry must
   have exactly these four keys:
     - "title":     a short noun phrase in the speaker's language (≤ 30 chars)
     - "start_idx": integer, the `idx` of the first record in the topic
     - "end_idx":   integer, the `idx` of the last record in the topic
     - "gist":      one sentence in the speaker's language summarizing the
                    topic (used later for cross-chunk merging — be concrete,
                    not generic)
   Topics must be contiguous and non-overlapping. The first topic's
   start_idx must equal <START_IDX>; the last topic's end_idx must equal
   <END_IDX>.
5. Final reply: ONE LINE in this exact format and nothing else:
   "Chunk <CHUNK_N>: <K> topics."

Hard rules:
- All output goes through the `write` tool. Your reply is truncated at
  10000 characters and the orchestrator only reads the one-line summary.
- Do not invent records. Do not modify any record text. You are only
  identifying boundaries and labeling them.
- Output JSON only — no markdown fences around the array.
```

---

## Stage 2 — Merge Topics (orchestrator does this itself, no workers)

You handle this stage. The per-chunk topic lists are tiny.

1. `glob_tool` with pattern `<session_dir>/intermediate/stage1/chunk_*/topics.json`. Sort by chunk number.
2. `read` every file. Hold all topics in working memory as a flat ordered list (chunk 1's topics, then chunk 2's, etc.), tagged with their source chunk.
3. **Merge adjacent topics across chunk boundaries** when they are the same subject. Signals:
   - Same/near-identical `title`.
   - `gist` describes the same subject (do a semantic read, not string match).
   - One topic's `end_idx` is within ~15 of the next topic's `start_idx` (overlap region from Stage 1 chunking).
   When merging, use the earlier topic's `title` (or the better-phrased of the two), keep the earliest `start_idx`, the latest `end_idx`, and concatenate gists (or pick the more informative one).
4. **Within a single chunk, do not merge** — Stage 1 already decided those boundaries.
5. Assign each merged topic a stable `topic_id`: `T<seq>` where `<seq>` is a 1-based counter in the merged order. Pad to 2 digits: `T01`, `T02`, ...
6. Call `write` to create `<session_dir>/intermediate/topic_map.json`:
   ```json
   [
     {"topic_id": "T01", "title": "...", "idx_range": [start, end]},
     ...
   ]
   ```
   Topics must be in `idx_range[0]` ascending order, contiguous (each topic's start = previous topic's end + 1) and covering the full `[1, last_idx]` range of the session.

If `<session_dir>/intermediate/topic_map.json` exists and no stage token forced regen, you may skip this stage.

---

## Stage 3 — Write per-topic Markdown (parallel workers, one per topic)

1. `read` `<session_dir>/intermediate/topic_map.json` and `<session_dir>/intermediate/normalized.jsonl`. Keep both as strings — call them `TOPIC_MAP` and `NORMALIZED`.
2. For each topic in `topic_map.json`:
   - If `<session_dir>/intermediate/topics/<topic_id>.md` exists and no stage token forced regen, skip.
   - Else, slice `NORMALIZED` to just the records whose `idx` is in this topic's `idx_range`. Call this `SLICE_JSONL` (a string of those JSON lines, one per line).
3. For each non-skipped topic, call the `agent` tool **once in parallel** (batch the calls in a single message). The `prompt` is `WORKER PROMPT — STAGE 3` below with **every** placeholder literally substituted. Before sending, confirm zero `<...>` or `<<<...>>>` markers remain.
4. After all workers return, print `Stage 3: <K> topics done` for the session.

### WORKER PROMPT — STAGE 3

> Substitute `<SESSION_DIR>`, `<TOPIC_ID>`, `<TITLE>`, `<START_IDX>`, `<END_IDX>`, `<HAS_TIMESTAMPS>` (the string `true` or `false`), and `<<<SLICE_JSONL>>>` everywhere, then send as the `prompt` argument to the `agent` tool.

```
You are a single-purpose worker. Your only job is to write the skim-read
markdown for ONE topic of a transcript. You may not use the `agent` tool.

Available tools: write. Do not use any others — your input is given inline.

Topic id:    <TOPIC_ID>
Topic title: <TITLE>
Idx range:   [<START_IDX>, <END_IDX>]
Has timestamps: <HAS_TIMESTAMPS>
Output file: <SESSION_DIR>/intermediate/topics/<TOPIC_ID>.md

The normalized records for this topic (already loaded — do NOT read from disk):

<<<SLICE_BEGIN>>>
<<<SLICE_JSONL>>>
<<<SLICE_END>>>

Each line above is a JSON object {"idx": N, "ts": "HH:MM:SS" or null, "text": "..."}.

Your task — produce a skim-read version that PRESERVES THE ORIGINAL WORDING.

You may ONLY:
  - Remove filler words (e.g. Chinese: 那个/就是说/对吧/嗯/啊; English: um, like, you know).
  - Merge near-duplicate sentences where the speaker said the same thing
    two or three times in a row — keep the most complete phrasing, drop the rest.
  - Fix obvious slips of the tongue (e.g. wrong word immediately corrected).
  - Join consecutive records into flowing paragraphs.

You MUST NOT:
  - Paraphrase or "say it better".
  - Add your own explanation, commentary, or background.
  - Change the speaker's tone, register, or terminology.
  - Add structure the speaker did not have (no bullet lists invented from prose).
  - Translate.

Output format — the markdown file must look like:

```
## <TITLE>

[anchor] paragraph 1 (in the speaker's original wording, fillers removed)

[anchor] paragraph 2 ...
```

Where `[anchor]` is:
  - `[HH:MM:SS]` (the `ts` of the first record in that paragraph) if Has timestamps is `true`
  - `[L:<idx>]` (the `idx` of the first record in that paragraph) if Has timestamps is `false`

Use 2–6 paragraphs total — pick natural pause points within the topic. Each
paragraph gets exactly one anchor at its start. The first paragraph's anchor
must correspond to the first record in your slice (idx = <START_IDX>).

Call `write` to create the output file. Do NOT wrap the file in code fences.

Final reply: ONE LINE in this exact format and nothing else:
  "Topic <TOPIC_ID>: <P> paragraphs."

Hard rules:
- All output goes through the `write` tool. Your reply is truncated at
  10000 characters and the orchestrator only reads the one-line summary.
- Preserve the speaker's language. If the records are Chinese, write Chinese.
- Do not invent records or anchors. Every anchor must come from a real `ts`
  or `idx` in the slice above.
```

---

## Final Assembly (orchestrator does this itself, no workers)

1. `read` `<session_dir>/intermediate/topic_map.json`.
2. For each topic in `idx_range[0]` ascending order, `read` `<session_dir>/intermediate/topics/<topic_id>.md`. Hold them in order.
3. Build `<session_dir>/digest.md` with this structure:
   ```
   # <session name> — Digest

   <P> topics, <R> source records.

   ## Contents

   - [<anchor>] [<title>](#<topic_id>)
   - ...

   ---

   <body of each topic markdown, in order, separated by `\n\n`>
   ```
   - `<session name>` = the input file stem (e.g. `2025-05-01`).
   - `<anchor>` in the Contents list is the anchor of each topic's first paragraph (extract it from the topic markdown — it's at the start of the first paragraph after the `## <TITLE>` line).
   - `<topic_id>` slug for the anchor link: lowercase the `topic_id` (e.g. `t01`).
4. Call `write` to create `<session_dir>/digest.md`.

The existence of `<session_dir>/digest.md` is the marker that this session is done. **Do not delete intermediates yet** — Stage 4 needs `intermediate/topic_map.json` and `intermediate/topics/`.

---

## Stage 4 — Folder-level Categorization & Overview (orchestrator does this itself, no workers)

You handle Stage 4 yourself — no workers. It runs **once per folder**, after every session has its own `digest.md`. It exists because per-session topics are sliced too finely for a human skim (e.g. one livestream produces 25 micro-topics, with three of them just being "cups" labeled differently). Stage 4 lifts the view one level up: cross-session clustering + a written overview of the whole livestream/event.

**Skip condition**: if `<folder>/md/总论.md` already exists and `stage == None`, skip Stage 4. If `stage == "stage4"`, regenerate unconditionally.

### Stage 4a — Collect

1. `glob_tool` `<folder>/*/intermediate/topic_map.json`. For each match, the session name is the parent directory's name.
2. `read` every `topic_map.json`. In working memory, build a flat list:
   ```
   [
     {"session": "<session_name>", "topic_id": "T01", "title": "...", "idx_range": [s, e]},
     ...
   ]
   ```
3. If no `topic_map.json` files were found under `<folder>/*/intermediate/`, print `Stage 4: no per-session output to aggregate.` and stop Stage 4 (continue to cleanup if appropriate).

### Stage 4b — Categorize (you read all titles and decide)

You are the one doing the categorization. Do not spawn a worker — you have the full topic list in working memory and need to see all sessions at once to choose good category boundaries.

1. Survey every entry's `title`. Look for clusters: subjects that appear under multiple titles or across multiple sessions. The session name itself (e.g. "...第3部分（熄火，准备看球）") often hints at a major phase shift.
2. Choose **3–6 categories**. Each category gets:
   - `slug`: lowercase, hyphen-separated, ASCII (e.g. `stocks`, `relationships`, `city-talk`, `chat-banter`). You pick the slugs.
   - `name`: a short noun phrase in the speaker's language (e.g. `股票与时政`, `情感与人际`, `城市与发展`).
   - `description`: one sentence describing what falls in this category.
3. Assign **every** topic to exactly one category. Trivial pure-banter slots (e.g. T08 "话题277-290", T14 "聊天互动536-570") are fine to assign to a `chat-banter` / `闲聊互动` category — do not drop them, but it's fine to give them a low-priority category.
4. Categories should be qualitatively distinct. If two categories overlap heavily, merge them. If one category swallows >70% of topics, split it.
5. `write` `<folder>/md/categories.json`:
   ```json
   {
     "categories": [
       {
         "slug": "sports-football",
         "name": "体育与足球",
         "description": "讨论足球比赛、战术分析、球队阵容、体育评论",
         "topics": [
           {"session": "第1部分", "topic_id": "T02"},
           {"session": "第4部分", "topic_id": "T01"}
         ]
       },
       ...
     ]
   }
   ```
   Order categories by descending total record count (sum of `end_idx - start_idx + 1` across their topics). Within each category, order topics by `(session_sort_key, idx_range[0])` so the resulting document reads chronologically.

### Stage 4c — Write per-category documents

For each category in `categories.json`:

1. For every topic listed, `read` `<session>/intermediate/topics/<topic_id>.md`. Hold the contents.
2. Build `<folder>/md/<category-name>.md` (use the `name` field as the filename, e.g. `体育与足球.md`):
   ```
   # <name>

   <description>

   <P> 条原文片段，来自 <S> 个 session。

   ## 目录

   - [<session_name>] [<topic title>](#<session_slug>-<topic_id_lower>)
   - ...

   ---

   ## <session_name> · <topic title>

   <body of the topic's markdown — the same `[anchor]` paragraphs as in the session digest>

   ---

   ## <next session_name> · <next topic title>
   ...
   ```
   - `<session_slug>` is `<session_name>` with spaces/CJK punctuation replaced by hyphens, lowercased where possible — this is just for anchor links, exact form is your choice as long as anchors are unique within the file.
   - Do not paraphrase or rewrite the topic bodies. Pass them through verbatim. You are concatenating, not editing.
3. `write` the file.

### Stage 4d — Write the overview

After all category files are written, write `<folder>/md/总论.md` — the cross-session synthesis the user reads first.

You compose this yourself (no worker). You have already read every topic title + every category body, so you have the full picture in working memory. The overview must include:

```
# <folder name> — 总论

## 本期主题

<2-4 sentences in the speaker's language stating what this whole livestream/event was about. Not a topic list — a thesis.>

## 阶段划分

<Walk through the sessions in order. For each session, state what dominated it (which categories were active) and what shifted vs the previous session. Cite session names in full.>

例：
- **第 1 部分** — 以情感咨询开场，电话来访者占主线；股票/时政作为穿插。
- **第 2 部分** — 情感话题延伸到摩羯/天平/双鱼性格分析；后段过渡到城市与直播业。
- ...

## 类别与彼此关系

<For each category in categories.json, one paragraph: what it covers, in which sessions it surfaced, and how it relates to neighboring categories. Make explicit which categories are the "spine" of the livestream and which are filler/branching topics.>

## 阅读建议

<2-3 sentences telling the reader where to start. e.g. "想了解直播脉络从本文 → 阶段划分即可；想看情感板块直接读 情感与星座.md；要复盘城市观点见 城市与职业发展.md。">

---

## 链接

- 类别文档：
  - [<name>](<category-name>.md)
  - ...
- 每场 session 的 digest（见 `parts/` 目录）：
  - [<session_name>](parts/<session_slug>.md)
  - ...
```

**Constraints on the overview:**
- Length budget: 400–800 Chinese characters (excluding the link section). Long enough to give shape, short enough to actually be read first.
- Do not invent topics the speaker did not cover. Anchor every claim to a category/session you can point at.
- The "彼此关系" paragraph is the highest-value part — it is the thing per-session digests cannot give the user. Spend the word count there.
- Write in the speaker's language (Chinese if the transcripts are Chinese).

`write` the overview to `<folder>/md/总论.md`. Existence of this file is the marker that Stage 4 is done.

---

## Stage 5 — Per-category Stitched Reading (parallel workers, one per category)

Stage 5 builds the **stitched reading layer**: for each category in `categories.json`, one worker takes the fragmented subtitle-style topic bodies and stitches them into something a reader can actually read end-to-end without the constant interruptions of timestamps, false starts, and out-of-order topics. The output is **not** an essay, **not** a 公众号长文, **not** a summary — it is the *same content* the speaker delivered, in the *same order of ideas*, but rewritten as connected prose instead of broken subtitle fragments.

This layer was added because the three earlier layers all have gaps:
- `md/parts/<场次>.md` — broken into short subtitle fragments with timestamps; reads as 字幕拼接，not as prose.
- `md/<category-name>.md` (Stage 4c) — same fragments, just regrouped by category instead of by time.
- `md/总论.md` (Stage 4d) — too thin, gives shape but no content.

Stage 5 fills the middle as **the layer the user actually reads**.

### Stage 5 — Orchestrator Procedure

1. `read` `<folder>/md/categories.json`. If it is missing, print `Stage 5: missing categories.json (run Stage 4 first).` and stop Stage 5.
2. For every category, compute the expected output path: `<folder>/md/notes/<category.name>.md` (use the descriptive Chinese `name`, same convention as Stage 4c).
3. Decide which categories to (re)run:
   - If `$ARGUMENTS` contained `stage5`, run all categories unconditionally.
   - Else, skip any category whose output file already exists.
4. If nothing to run, print `Stage 5: all notes already exist.` and continue to Moveto.
5. For every category that needs running, gather its inputs: `read` each `<session>/intermediate/topics/<topic_id>.md` named under that category's `topics` array. Concatenate them in the same order as Stage 4c (chronological by `(session_sort_key, idx_range[0])`), separated by `\n\n---\n\n` with a short header line `## <session_name> · <topic_id>` before each body. Call this concatenated string `TOPIC_BODIES`.
6. For each category, call the `agent` tool **once in parallel** (batch all category workers in a single message with multiple tool calls). The `prompt` is `WORKER PROMPT — STAGE 5` below, with every placeholder literally substituted. Before sending, confirm zero `<...>` or `<<<...>>>` markers remain in the final prompt string.
7. After all workers return, print `Stage 5: <K> category notes done` and proceed to Moveto.

### WORKER PROMPT — STAGE 5

> Substitute `<FOLDER>`, `<CATEGORY_NAME>`, `<CATEGORY_DESCRIPTION>`, `<TOPIC_COUNT>`, `<SESSION_COUNT>`, and `<<<TOPIC_BODIES>>>`. Then send as the `prompt` argument to the `agent` tool.

```
You are a single-purpose worker. Your only job is to stitch fragmented
subtitle bodies for ONE category into something a human can read
straight through. You may not use the `agent` tool.

Available tools: write. Do not use any others — your input is given inline.

Category name:        <CATEGORY_NAME>
Category description: <CATEGORY_DESCRIPTION>
Topic count:          <TOPIC_COUNT>
Session count:        <SESSION_COUNT>
Output file:          <FOLDER>/md/notes/<CATEGORY_NAME>.md

The aggregated topic bodies for this category (already loaded — do NOT
read from disk). Each section is one topic from one session. They are
in chronological order.

<<<TOPIC_BODIES_BEGIN>>>
<<<TOPIC_BODIES>>>
<<<TOPIC_BODIES_END>>>

# What you are doing

You are NOT writing an essay. You are NOT writing a 公众号 article.
You are NOT summarizing. You are NOT analyzing.

You are taking subtitle fragments — short broken lines like
`[00:12:34] 那个就是说啊 我觉得吧` — and rewriting them so they
read as connected sentences and paragraphs. The reader should be
able to read your output from top to bottom like a transcript of a
conversation, except in proper sentences instead of in 字幕碎片
form, so they don't have to constantly mentally reassemble what the
speaker was saying.

Think of it as: **the same content the speaker actually delivered,
in the same order he delivered it, but with the subtitle scaffolding
removed**.

# Concretely, what to do

1. Go through TOPIC_BODIES top to bottom in order.
2. For each topic body: drop the `[HH:MM:SS]` and `[L:N]` anchors,
   merge the broken lines into full sentences, drop fillers and
   stuttering, fix obvious slips, but **keep the same wording the
   speaker actually used** wherever it already makes sense in
   written form.
3. When the speaker repeats the same point three times in a row,
   keep the most complete phrasing once.
4. Where one topic flows naturally into the next, just continue
   writing — you can drop topic boundaries that no longer serve
   the reader.
5. Where the topic actually shifts to a new sub-subject, use a
   short `##` heading. The heading is just a navigation aid; it
   should describe what the speaker is talking about in that
   stretch in simple plain words (e.g. `## 谈到摩羯男的相处方式`,
   not `## 摩羯座情感模式的内在逻辑`).
6. Cross-session merging is fine — if the speaker came back to the
   same sub-subject later, you can put those stretches under the
   same heading and continue the flow. But if it really does feel
   like a separate thread, give it its own heading.

# 长度

Length is whatever falls out of doing the work above honestly. Do not
try to hit any specific target. If the speaker spent a lot of time on
this category, the file is long. If he only touched it briefly, the
file is short. **Never pad. Never trim to look balanced.**

# 改写的尺度（这是最容易跑偏的地方）

You are de-fragmenting, not rewriting. Imagine the reader is watching
you take a transcript and clean it up by hand:

- Drop fillers (`那个`、`就是说`、`对吧`、`嗯`、`啊`、`这个那个`).
- Drop the `[HH:MM:SS]` / `[L:N]` anchors entirely. They do not appear
  in your output.
- Merge broken short subtitle lines that obviously belong to one
  sentence into one sentence.
- When the speaker says the same thing three times in slightly
  different ways, keep the clearest version once.
- Fix obvious slips of the tongue.
- Insert a comma or period where the subtitle break ate one.

You do NOT:

- Rewrite the speaker's casual wording into 书面语 / 文绉绉. If he
  said「我觉得这破玩意儿不靠谱」, you write「我觉得这破玩意儿不靠谱」,
  not「我认为此事物可信度存疑」.
- Add transition phrases the speaker did not use ("因此"、"由此可见"、
  "综上所述"、"反过来说" — only use these if the speaker actually said
  them).
- Add framing sentences explaining what the speaker is about to say
  or just said ("接下来作者谈到..."、"作者认为..."、"以上就是作者
  关于 X 的看法" — none of this. Just keep writing what the speaker
  said).
- Build an argument out of his points (no "他的核心观点是..."、
  no "可以分为三个层次..."). The structure is whatever the speaker
  actually used.
- Generalize from examples or extract patterns. If he tells three
  stories, you write three stories — you do not summarize them
  into "这反映了 X 的规律".
- Add an opening framing paragraph or a closing reflection
  paragraph. No 导言, no 结语, no 总结.
- Add commentary, evaluation, or "the takeaway is..." anywhere.
- Use bullet points unless the speaker himself was listing items
  ("第一是 A、第二是 B、第三是 C"). Default to running prose.
- Insert names, numbers, places, dates, or claims that aren't in
  TOPIC_BODIES.
- Translate. If the bodies are Chinese, the output is Chinese.

# Tone test

If your draft reads like a 公众号 essay, you have over-rewritten.
Walk it back toward the speaker's own voice. The right tone is
"recorded conversation, cleaned up just enough to read smoothly."

# 输出与签收

Call `write` to create `<FOLDER>/md/notes/<CATEGORY_NAME>.md`. Do
NOT wrap the file in code fences.

File shape:

```
# <CATEGORY_NAME>

<the stitched prose. Use `##` headings as section breaks where the
speaker shifted sub-subject. No 导言, no 结语.>

---
来源：本文基于 `<FOLDER>/md/<CATEGORY_NAME>.md`（共 <TOPIC_COUNT> 段原文，跨 <SESSION_COUNT> 个 session）整理。
```

Final reply: ONE LINE, format exactly:
  "Category <CATEGORY_NAME>: done."

Do not include anything else in the reply. The orchestrator only
reads this one line.
```

---

## Moveto (after Stage 5, or at end of single-file mode)

After all deliverables (per-session `digest.md`, plus `md/` folder-level files including Stage 5 notes) are confirmed written:

1. **Move source files** to `<folder>/srt/`: for each processed session, move `<folder>/<name>.srt` → `<folder>/srt/<name>.srt` (use `move` on Windows, `mv` on Linux/macOS). Create the `srt/` and `md/parts/` directories first if needed.
2. **Copy digest files** to `<folder>/md/parts/`: for each processed session, copy `<session_dir>/digest.md` to `<folder>/md/parts/第<序数>部分.md`. Create `md/parts/` first if needed. Use the numeric part from the session name (e.g. `2026-05-09二楼第1部分` → `第1部分.md`). If the session name doesn't follow this pattern, use the file stem as the md name.
3. If Stage 4 ran, the category files and `总论.md` are already in `<folder>/md/`.
4. If Stage 5 ran, the per-category notes are already in `<folder>/md/notes/`.

---

## Cleanup (after moveto, or at end of single-file mode)

After Moveto, remove every session's intermediates in one pass. Only run this once Moveto has succeeded.

For each processed session directory, delete:

```
<session_dir>/intermediate/   (entire folder)
```

On Windows, use the `bash` tool. Example for one session:
```bash
rm -rf "<session_dir>/intermediate"
```

What remains after cleanup:
- Per session: `subtitles/` (copy of source), `digest.md`.
- At the folder root: `srt/` with source files, `md/` with `总论.md`, `categories.json`, `<category-name>.md` files (if Stage 4 ran), and `md/parts/` with per-session digests.

> **为什么把 cleanup 推到最后**: Stage 4 需要每场的 `intermediate/topic_map.json` 和 `intermediate/topics/<TID>.md` 来做跨场聚类与拼接。如果每场 digest 后立刻清，Stage 4 就没料可用。统一在 Stage 4 + Moveto 完成后清，多花的只是磁盘临时占用。
>
> **如果 Stage 4 失败**: 不要清理。保留所有中间文件，方便排查后重跑 `stage4`。
>
> **如果 Moveto 失败**: 不要清理。保留所有中间文件，方便排查。

---

## Notes on placeholders and substitution

Every placeholder in a worker prompt is wrapped in angle brackets — `<NAME>` for short strings, `<<<NAME>>>` for large inline payloads. Before sending any worker prompt:

1. Replace every placeholder with its real value.
2. Scan the final string and confirm zero literal angle-bracket placeholders remain (search for `<` followed by capital letters).
3. Then call the `agent` tool.

Workers are isolated: they cannot see this document, cannot spawn further agents, and cannot read other sessions. All cross-stage data flows through files in `<session_dir>` (or inline payloads in the prompt for Stage 3 and Stage 5).
