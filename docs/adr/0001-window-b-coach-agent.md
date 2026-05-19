# ADR 0001 — Window B 是 opt-in 询问式的成长教练

> Status: Accepted (2026-05-19)
> Decider: @hiyad
> Context: R1.5 设计，grill-with-docs 会话

## Context

OhMyCode Desktop 的 Window B（"小柚"）经历了三轮定位演化：

- **v1**（M2.2）—— 细节讲解员，每个工具调用后讲一段原理。结果：用户反馈"讲一些很简单、没什么好解说的东西也会出教程，根本不需要"。
- **v2**（R1.A 草稿）—— 完整 coding agent + 教练人格，每 TurnComplete 自动反思，使用 `[silent]` 沉默 sentinel。但宏观视角默认每段都讲。
- **v3**（本 ADR）—— **宏观视角降级为用户 opt-in 询问式**。

## Decision

### 1. 触发 3 种（覆盖 A turn 的全生命周期）

- **`user_input`** — 用户在 A 区刚发消息那一刻，B 立即激活第一次
- **`turn_complete`** — A 完成 turn 后，B 再激活一次
- **`user_explicit`** — 用户 @B 显式发消息（任何时机）

删除之前 plan 里的 `tool_executing` (3s delay) / `repeated_error` / `long_wait` / `plan_drafted` 自动触发。

**A 跑越久 / 越复杂，B 与用户来回越多机会**——这是 B 填补"等待空隙"的核心价值。

### 2. B 的核心输出形态 = 询问式

B **不主动展开任何内容**。默认产出形态是：

- **简短识别**（1-3 句话）：注意到这件事里可能值得想的角度
- **询问**：是否要展开聊聊？

**不强加字数限制**。用户 @B 同意展开后，B 充分讲透——长短由内容决定，不由 prompt 框死。

### 3. `[silent]` 仍是 fallback

当 B 判断这次没什么值得识别 / 询问，输出 `[silent]` 沉默。

### 4. 微观 / 宏观对待方式一致

B 识别到的角度可以是：

- **微观**：当前任务的 why / pattern / transfer
- **宏观**：AI 时代成长方向（AI 接什么 / 人学什么 / 能力 vs 品味 / 杠杆 vs 重复 / 思考边界）

**两类都用询问式**——不再区分"宏观要 opt-in 微观自动讲"。所有展开都 opt-in。

### 5. 用户判定的 awareness 仍重要

B 仍要判断用户当前是否在赶 / 是否烦扰：

- 用户消息节奏快 / 含"急/快/赶"——B 倾向 `[silent]`，不打断
- B 最近 N 次询问已经够多——别再问
- 用户问过的问题不要重复问

### 4. `[silent]` 沉默 sentinel

当 B 判断这次没什么值得讲，输出**整 turn 唯一 token** `[silent]`（case-insensitive，前后空白允许）。后端 `TurnComplete` 时整体检测，suppress 整段、推 `b_silent` event 让前端 spinner 收。

### 5. B 工具能力 = A 同等

read / write / edit / bash / glob / grep / web_fetch 全部能调，**审批走 PermissionPanel**。但 prompt 教 B "绝大多数场景只读 / 不替用户写"。

历史回溯：B 通过 `glob` 扫 `~/.ohmycode/projects/<slug>/sessions/*/meta.json`，按需 `read` 某 session 的 a/b-messages.json。默认不读，只在用户明确回溯（"上次" / "刚才" / "之前"）时调。

### 6. concept_dispositions 软参考

用户的 `learn / delegate / skip` 标记是**参考**不是硬约束。`learn` 重点讲、`delegate` 简略、`skip` 不主动提；但 B 看到关键洞察可破例，只是要解释为什么破例。

### 7. inspirations 文件夹空时

完全省略 prompt 中的 `## 灵感资源` 段（不留 placeholder）。

## Alternatives considered

- **宏观每段都讲**：被否决——用户反馈"讲简单内容也出教程"，且宏观说教会麻木。
- **宏观显式两段**：被否决——死板、说教感强。
- **宏观只在 @B 时讲**：接近但太被动——用户不问就永远看不到宏观，失去"AI 时代成长伙伴"的核心价值。
- **`[silent]` 严格大小写**：被否决——LLM 反活不够，case-insensitive + whitespace 容错更稳。
- **dispositions 硬约束**：被否决——B 会被框死，错失关键洞察。

## Consequences

- B turn 的平均 token 消耗下降（很多 turn 直接 `[silent]`）
- 用户看到的 B 输出会**显著减少**——从"每个 turn 都讲"变成"经常沉默 + 偶尔反思 + 极少询问宏观"
- 宏观视角对话需要用户主动接受才发生，**用户掌控感**强
- B 是 coding agent 但 prompt 偏向"只读"，写工具需用户审批——安全 + 体验柔和

## Implementation file

`desktop/server/growth_prompt.py` 的 `GROWTH_AGENT_PROMPT` 字符串是该 ADR 的实施载体。

## Related

- `CONTEXT.md` 小柚 / `[silent]` sentinel 词条
- `desktop/server/profile.py` `concept_dispositions` 字段
- `desktop/server/sessions.py` history 路径结构
