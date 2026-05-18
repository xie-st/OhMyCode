---
name: speedrun
description: Turn a chapter-organized problem set into chapter-by-chapter exam-prep lesson notes — three-stage pipeline (solve → graph → lessons) with global cross-chapter awareness. Use when user wants to cram for an exam from a textbook problem set.
---

# Speedrun — Exam-Prep Study Material Builder

> **Audience for this document**: the **orchestrator agent** that received `/speedrun`. You are responsible for driving the whole pipeline. The `agent` tool spawns workers; workers receive only the prompt you craft below — they never see this document. Treat the prompt blocks marked `WORKER PROMPT` as opaque payloads to be substituted and sent verbatim.

A three-stage pipeline that turns a chapter-organized problem set (markdown) into chapter-by-chapter lesson notes that are **internally self-contained** but **globally aware** of cross-chapter dependencies.

## Pipeline Shape

| Stage | Who runs it | Why |
|---|---|---|
| Stage 1 — solve & extract | one **worker** (via `agent` tool) per chapter | per-chapter context isolation; one chapter's content never pollutes another |
| Stage 2 — merge into graph | the **orchestrator** itself, no workers | needs all chapters visible at once to deduplicate |
| Stage 3 — write lessons | one **worker** per chapter | same as Stage 1; plus you embed the global graph into each worker's prompt |

A "worker" is a fresh agent spawned via the `agent` tool. **Workers must not spawn further agents** — depth is limited and the pipeline does not need it. You enforce this by including the line `You may not use the agent tool.` in every worker prompt.

## Input Contract

The user must have prepared:

```
workspace/speedrun/
└── input/
    ├── ch01.md      # one markdown file per chapter
    ├── ch02.md      # filename (sans extension) becomes the chapter ID
    └── ...
```

If `workspace/speedrun/input/` is missing or empty after step 1 of Stage 1, **abort and tell the user** to populate it. Do not invent chapter names.

## Arguments — `$ARGUMENTS`

| Value | Behavior |
|---|---|
| *(empty)* | Run Stage 1 → 2 → 3 in order. Skip a per-chapter step if its output already exists. |
| `stage1` / `stage2` / `stage3` | Run only that stage, regenerating its output unconditionally. |

## Output Layout

```
workspace/speedrun/
├── stage1_output/<CHAPTER>/
│   ├── solutions.md
│   └── knowledge_points.json
├── stage2_output/
│   ├── graph.json
│   └── style_guide.md
└── stage3_output/<CHAPTER>/
    └── lesson.md
```

Throughout this document `<CHAPTER>` is the input filename without `.md` and without directory prefix. Example: `workspace/speedrun/input/第一章习题.md` → `<CHAPTER>` = `第一章习题`.

---

## Stage 1 — Orchestrator Procedure

1. Call `glob_tool` with pattern `workspace/speedrun/input/*.md`. If empty, abort per Input Contract.
2. For each glob result, derive the real `<CHAPTER>` string. Do not abbreviate, do not transliterate.
3. If `$ARGUMENTS` is empty and `workspace/speedrun/stage1_output/<CHAPTER>/knowledge_points.json` already exists, skip this chapter.
4. For each remaining chapter, call the `agent` tool exactly once. The `prompt` argument must be the `WORKER PROMPT — STAGE 1` block below with **every** `<CHAPTER>` literally replaced by the real chapter string. Before calling, scan your final prompt string and confirm zero occurrences of the literal seven-character sequence `<CHAPTER>` remain.
5. After all `agent` calls return, print a one-line summary per chapter using the worker's reply.

### WORKER PROMPT — STAGE 1

> Substitute `<CHAPTER>` everywhere, then send as the `prompt` argument to the `agent` tool.

```
You are a single-purpose worker. Your only job is to solve one chapter of a
problem set and write two output files. You may not use the `agent` tool.
You have no awareness of other chapters and must not try to read them.

Available tools: read, write, glob_tool, grep, bash. Do not use any others.

Chapter name: <CHAPTER>
Input file:   workspace/speedrun/input/<CHAPTER>.md
Output dir:   workspace/speedrun/stage1_output/<CHAPTER>/

Steps (do these in order, no others):

1. Call `read` on the input file. If it errors, your final reply must be
   exactly: "READ FAILED: <error message from read>" and you must stop.
2. Solve every problem in the file. Show reasoning steps for each.
3. Call `write` to create workspace/speedrun/stage1_output/<CHAPTER>/solutions.md
   containing all solutions. Use one `## Problem N` heading per problem,
   in the original problem order.
4. Identify the knowledge points actually used across the solutions.
   Call `write` to create workspace/speedrun/stage1_output/<CHAPTER>/knowledge_points.json
   as a JSON array. Each entry must have exactly these four keys:
     - "slug":        a lowercase-hyphenated id you choose freely
     - "name_zh":     the Chinese name of the knowledge point
     - "description": one or two sentences explaining the concept
     - "problem_refs": array of integers — the problem numbers using it
5. Final reply: ONE LINE in this exact format and nothing else:
   "Processed N problems, extracted M knowledge points."

Hard rules:
- All real content goes through the `write` tool. Do not put solutions or
  knowledge points in your reply text — your reply is truncated at 10000
  characters and the orchestrator only reads the one-line summary.
- The `write` tool must be called at least twice (solutions.md, knowledge_points.json).
- Do not invent problems. Solve only what is in the input file.
```

---

## Stage 2 — Orchestrator Procedure (no workers)

You do this stage yourself. The merged knowledge-point set is small enough.

1. Call `glob_tool` with pattern `workspace/speedrun/stage1_output/*/knowledge_points.json`.
2. `read` every file. Hold all entries in working context.
3. Merge them into one global graph:
   - **Deduplicate**: same concept under different slugs → choose one canonical English-friendly `id`. Record original slugs in `aliases`.
   - **Edges**: where knowledge point A is a prerequisite for B, add `{from: A, to: B, type: "prereq"}`.
   - **Cognitive gaps**: where chapter N introduces a concept that depends on something never properly built up earlier, record it. These annotations are the highest-value output of this stage.
4. Call `write` to create `workspace/speedrun/stage2_output/graph.json` with this shape:
   ```json
   {
     "nodes": [
       {
         "id": "canonical-id",
         "name_zh": "...",
         "description": "...",
         "appears_in": ["第一章习题", "第二章习题"],
         "aliases": ["original-slug-1", "original-slug-2"]
       }
     ],
     "edges": [
       {"from": "id-a", "to": "id-b", "type": "prereq"}
     ],
     "cognitive_gaps": [
       {"chapter": "第二章习题", "concept": "id-x", "issue": "introduced without building up id-y first"}
     ]
   }
   ```
5. Call `write` to create `workspace/speedrun/stage2_output/style_guide.md` — at most 30 lines covering:
   - Tone (study-aid voice, e.g. semi-formal Chinese)
   - Terminology rules (e.g. pair Chinese with English on first use)
   - How to phrase cross-chapter callouts (e.g. "回顾第 1 章的 X" / "为第 3 章的 Y 做铺垫")
   - Worked-example formatting

---

## Stage 3 — Orchestrator Procedure

1. `read` `workspace/speedrun/stage2_output/graph.json` and `workspace/speedrun/stage2_output/style_guide.md`. Keep both contents as strings — call them `GRAPH_CONTENT` and `STYLE_CONTENT`.
2. `glob_tool` `workspace/speedrun/stage1_output/*/knowledge_points.json` to get the chapter list. Derive each `<CHAPTER>` by stripping the prefix and `/knowledge_points.json` suffix.
3. If `$ARGUMENTS` is empty and `workspace/speedrun/stage3_output/<CHAPTER>/lesson.md` already exists, skip that chapter.
4. For each remaining chapter, call the `agent` tool exactly once. The `prompt` argument is the `WORKER PROMPT — STAGE 3` block below with three substitutions:
   - `<CHAPTER>` → real chapter string
   - `<<<GRAPH_CONTENT>>>` → the full graph.json string from step 1
   - `<<<STYLE_CONTENT>>>` → the full style_guide.md string from step 1
   Before calling, confirm zero literal `<CHAPTER>`, `<<<GRAPH_CONTENT>>>`, or `<<<STYLE_CONTENT>>>` markers remain.
5. After all `agent` calls return, print a one-line summary per chapter.

### WORKER PROMPT — STAGE 3

> Substitute the three markers, then send as the `prompt` argument to the `agent` tool.

```
You are a single-purpose worker. Your only job is to write the lesson notes
for one chapter. You may not use the `agent` tool. You may not read or write
any chapter other than the one named below.

Available tools: read, write. Do not use any others.

Chapter name:   <CHAPTER>
Solutions file: workspace/speedrun/stage1_output/<CHAPTER>/solutions.md
Knowledge file: workspace/speedrun/stage1_output/<CHAPTER>/knowledge_points.json
Output file:    workspace/speedrun/stage3_output/<CHAPTER>/lesson.md

The global knowledge graph (already loaded for you, do NOT read from disk):

<<<GRAPH_BEGIN>>>
<<<GRAPH_CONTENT>>>
<<<GRAPH_END>>>

The style guide (already loaded for you, do NOT read from disk):

<<<STYLE_BEGIN>>>
<<<STYLE_CONTENT>>>
<<<STYLE_END>>>

Steps:

1. `read` the solutions file and the knowledge file for this chapter.
2. Write the lesson. It must satisfy all of:
   - Self-contained: a student reading just this lesson can learn the chapter.
   - Cross-chapter callouts: when a concept depends on a node from an earlier
     chapter (per the graph's `prereq` edges), insert a brief 「前情回顾」
     paragraph linking back. When this chapter introduces a concept later
     chapters build on, insert a brief 「为后文铺垫」 paragraph.
   - Cognitive-gap bridges: if this chapter appears in `cognitive_gaps`,
     explicitly address the gap with a bridging explanation.
   - Worked examples: use the solutions file as worked examples — cite by
     "Problem N" and reuse the existing derivations rather than re-deriving.
   - Style: follow the style guide above for tone, terminology, formatting.
3. `write` the lesson to the output file in one call.
4. Final reply: ONE LINE in this exact format and nothing else:
   "Generated lesson for <CHAPTER> (~N words)."

Hard rules:
- The `write` tool must be called exactly once, for the output file above.
- Do not put the lesson body in your reply text — your reply is truncated
  at 10000 characters and the orchestrator only reads the one-line summary.
```

---

## Verification (after a full run)

1. `stage1_output/<chapter>/solutions.md` and `stage1_output/<chapter>/knowledge_points.json` exist and are non-empty for every chapter.
2. `stage2_output/graph.json` parses as JSON; has ≥1 node and ≥1 edge.
3. Every `stage3_output/<chapter>/lesson.md` exists and contains at least one of `前情回顾` or `为后文铺垫`.
4. Single-stage rerun works: delete `stage3_output/`, run `/speedrun stage3`, confirm only Stage 3 runs.

## Iteration Tips

- Bad Stage 1 output → edit the `WORKER PROMPT — STAGE 1` block, then `/speedrun stage1`.
- Bad graph → edit Stage 2 procedure above, then `/speedrun stage2`. Stage 1 output is reused.
- Bad lesson tone → edit Stage 2's style-guide bullets (or hand-edit `style_guide.md`), then `/speedrun stage3`.
- For a brand-new problem set, do `/speedrun stage1` on one chapter first to verify the JSON schema before processing all chapters.

## Why This Architecture

- **Workers per chapter (Stage 1 & 3)**: a single context can't hold every chapter's full text; per-worker isolation gives each chapter a clean slate.
- **Orchestrator-only Stage 2**: cross-chapter deduplication needs every knowledge point visible at once.
- **Workers cannot spawn workers**: kept depth-1 because the agent depth limit is 2 ([ohmycode/tools/agent.py:7](ohmycode/tools/agent.py#L7)) and orchestrator already occupies one level. The `You may not use the agent tool.` line in worker prompts enforces this.
- **Worker reply 10k char limit** ([ohmycode/tools/agent.py:95-96](ohmycode/tools/agent.py#L95-L96)): all real output goes to disk via `write`; workers reply with one summary line only.
- **Disk-as-handoff**: each stage's output is a stable on-disk artifact, so any stage can be re-run independently.
