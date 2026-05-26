# 23. Next Page Agent

> 本文档定义 Sextant 第一版写作 Agent 如何逐页、逐段推进写作。这里不讨论实现方式，只讨论输入、输出、模式和数据流。

## 1. 定位

Next Page Agent 是 Sextant 第一版 Agent 的核心执行者。它不负责写完整小说，也不负责规划全书。它只负责在当前 Memory、当前 POV、当前角色状态和 Storytelling Control Layer 的约束下，帮助作者推进下一小步。

```text
当前场景 + 当前 POV + 当前角色压力
  ↓
角色自然行动
  ↓
故事讲述控制层：cast / dramatization / scene mode / prose contract
  ↓
下一步候选
  ↓
候选正文
  ↓
作者接受后进入 Memory
```

## 2. 三种工作模式

| 模式 | 目标 | 输出 |
|---|---|---|
| Suggest Next Beat | 只给下一步方向，不写正文 | BeatCandidate 列表 |
| Draft Next Passage | 写下一小段正文 | DraftCandidate |
| Rewrite Current Page | 打磨当前页，不推进剧情 | DraftCandidate |

## 3. Suggest Next Beat

Suggest Next Beat 只回答：角色自然会做什么、故事下一小步有哪些可能。它仍应经过 Storytelling Control Layer，以避免只复用旧角色或给出没有戏剧转折的方向。

```mermaid
sequenceDiagram
    participant Pack as Writing Context Pack
    participant Agency as Character Agency Pass
    participant Story as Storytelling Control Layer
    participant Agent as Next Page Agent
    participant Author as 作者

    Pack->>Agency: 当前角色状态和场景压力
    Agency->>Story: 角色自然行动候选
    Story->>Story: Role Need / Scene Mode / Dramatic Form
    Story->>Agent: RoleSlot / CharacterCastingDecision / SceneSequelMode / ProseRenderingContract
    Agent->>Author: 返回 1-5 个 BeatCandidate
```

BeatCandidate 结构：

| 字段 | 说明 |
|---|---|
| beat_id | 候选方向 ID |
| summary | 下一步发生什么 |
| driver_character | 主要推动角色 |
| agency_rationale | 为什么这个角色会这么做 |
| storytelling_rationale | 为什么这个 beat 有故事推进、冲突或转折 |
| cast_decision | 是否复用旧角色或创建新角色 |
| tension | 该 beat 制造的张力 |
| agent_review_findings | 可能的 AgentReviewFinding 列表，risk_type 使用 [26-agent-review-policy.md](26-agent-review-policy.md) |
| memory_refs | 相关 MemoryPage / CanonicalEvent / SourceSpan |

## 4. Draft Next Passage

Draft Next Passage 生成下一小段正文。它必须遵守 Writing Context Pack 和 Prose Rendering Contract。

输入：

| 输入 | 说明 |
|---|---|
| Writing Context Pack | 当前 canon、POV、角色、风险、风格 |
| Character Agency Pass | 角色欲望、压力、自然行动 |
| Storytelling Control outputs | RoleSlot、CharacterCastingDecision、DramaticBehaviorPlan、SceneSequelMode |
| Prose Rendering Contract | 最终写作契约 |
| Selected Beat | 作者选定或 Agent 推荐的下一步方向 |
| Passage Length | 建议一小段到一页 |
| Target Position | `target_source_id`、`target_version_id`、`target_scene_id`、`affected_range`、`base_hash` |

输出：

| 输出 | 说明 |
|---|---|
| DraftCandidate | 候选正文 |
| rationale | 为什么这样写 |
| used_context | 使用了哪些记忆和 contract |
| agent_review_findings | AgentReviewFinding，不是正式 ReviewItem |
| revision_options | 可选修改方向 |

## 5. Rewrite Current Page

Rewrite Current Page 不推进剧情，只打磨已有文本。但它仍应经过 Storytelling Control Layer，尤其是 Dramatization Layer 和 Prose Rendering Contract。

它可以处理：

- 语言节奏；
- 叙述距离；
- POV 漂移；
- 角色声音；
- 过度解释；
- 内心戏流水账；
- 对话自然度；
- 意象和场景氛围；
- 缺少 scene / sequel turn 的段落。

```mermaid
flowchart TD
    A[Current Page Text] --> B[Writing Context Pack]
    A --> C[Target Position\nsource_id / version_id / affected_range / base_hash]
    B --> D[Storytelling Control Layer]
    C --> D
    D --> E[Dramatic Behavior Plan / Prose Contract]
    E --> F[DraftCandidate: revised page]
    F --> G[Agent Review]
    G --> H[作者接受或继续改]
```

Rewrite 不应：

- 偷偷改变已发生事件；
- 引入新 canon；
- 修复矛盾时不提示作者；
- 把未确认 proposed 信息写成事实；
- 在没有 `affected_range` 和 `base_hash` 的情况下覆盖原文；
- 把角色内心状态直接展开成说明文。

## 6. Next Page Agent 主流程

```mermaid
flowchart TD
    A[Writing Context Pack] --> B[Character Agency Pass]
    B --> C[Storytelling Control Layer]
    C --> D[Role Need / Cast Expansion]
    C --> E[Dramatic Behavior Plan]
    C --> F[Scene / Sequel Mode]
    C --> G[Prose Rendering Contract]
    D --> H{模式}
    E --> H
    F --> H
    G --> H
    H -->|Suggest| I[BeatCandidate]
    H -->|Draft| J[DraftCandidate]
    H -->|Rewrite| K[DraftCandidate: revision]
    I --> L[作者选择]
    L --> J
    J --> M[Agent Review]
    K --> M
    M --> N{是否可交给作者?}
    N -->|风险可说明| O[返回候选 + AgentReviewFinding]
    N -->|严重越界| P[返回拒绝/重写建议]
```

## 7. Agent 输出要求

所有输出都应带有：

| 字段 | 说明 |
|---|---|
| candidate_text | 候选正文或候选方向 |
| mode | suggest / draft / rewrite |
| target_source_id | 目标 RawSource，可为空 |
| target_version_id | 候选基于哪个 SourceVersion |
| target_scene_id | 候选针对的场景，可为空 |
| affected_range | append / replace 的目标范围，可为空 |
| base_hash | 生成时目标文本的基线 hash |
| memory_used | 使用了哪些 Memory 对象 |
| evidence_refs | 关键证据引用 |
| storytelling_outputs | RoleSlot、CharacterCastingDecision、SceneSequelMode、DramaticBehaviorPlan、ProseRenderingContract 摘要 |
| agent_review_findings | 草稿阶段风险说明，不是正式 ReviewItem |
| author_options | 作者可以接受、部分接受、修改、重写或换方向 |

## 8. 生成约束

Next Page Agent 必须遵守：

- 不使用 POV 角色不知道的信息；
- 不把 proposed / disputed 当作 canon；
- 不强行解决 open ReviewItem；
- 不违背 Character Agency Profile；
- 不绕过 Storytelling Control Layer 直接写正文；
- 不绕过作者接受；
- 不自动写入 Memory；
- 不在没有 SourceDelta / SourceSpan 的情况下创建正式 ReviewItem；
- 不生成过长文本作为第一版默认行为。

## 9. 失败模式

| 失败模式 | 说明 | 应对 |
|---|---|---|
| Plot forcing | 为剧情强迫角色做不自然的事 | 回到 Character Agency Pass |
| Cast compression | 因为 Memory 里已有角色就过度复用旧角色 | 运行 Role Need / Cast Expansion |
| Canon leak | 使用未确认或 POV 不知道的信息 | 生成 AgentReviewFinding / 修改候选 |
| Inner-state dumping | 把角色内心状态平铺成说明 | 回到 Dramatization Layer |
| Style drift | 写得不像当前作品 | 重新读取 Style Memory / Prose Contract |
| No turn | 段落没有 goal、opposition、decision 或 hook | 重新判断 Scene / Sequel Mode |
| Over-generation | 一次写太多，越过作者控制 | 缩短为 passage / beat |
| Unsafe rewrite | 无 target range / base hash 却试图替换原文 | 要求重新定位目标文本 |
| Self-canonization | Agent 生成后自己当事实使用 | 只允许作者接受后进入 SourceDelta |

## 10. 结论

Next Page Agent 的核心不是“写得多”，而是“在正确约束下写下一小步”。

```text
小步推进，比一次生成整章更适合长期小说写作；
Storytelling Control Layer 确保这个小步不是流水账，也不是被已有角色锁死。
```
