# 05. Review 与风险契约

> 本文档定义风险提示、AgentReviewFinding、ReviewItem 和非阻塞处理策略。它不定义最终 Review 面板 UI。

## 1. 核心原则

风险提示的目标是保护作者的 canon，而不是打断作者。

```text
Risk informs.
Review protects.
Writing continues.
```

Sextant 必须区分两类风险对象：

| 对象 | 来源 | 是否正式 Memory 对象 | 作用 |
|---|---|---:|---|
| AgentReviewFinding | Agent / Story Skill 在候选或当前段落中发现 | 否 | 草稿层风险提示，帮助作者选择或修改候选 |
| ReviewItem | Memory Conflict Policy / Review Policy 产生 | 是 | 正式风险、冲突或 canon promotion 阻断事项 |

## 2. AgentReviewFinding

`AgentReviewFinding` 属于草稿层。它可以附在候选、改写、风险检查结果或解释上，但不能直接成为正式 `ReviewItem`。

```ts
type AgentReviewFinding = {
  id: string
  action_request_id: string
  candidate_id?: string
  risk_type:
    | "pov_risk"
    | "knowledge_risk"
    | "canon_risk"
    | "unresolved_risk"
    | "continuity_risk"
    | "forbidden_knowledge_leak"
    | "non_pov_mind_reading"
    | "target_range_risk"
    | "character_risk"
    | "agency_break_risk"
    | "control_risk"
    | "cast_reuse_risk"
    | "cast_creation_risk"
    | "cast_focus_risk"
    | "cast_complexity_risk"
    | "cast_policy_violation"
    | "style_risk"
    | "exposition_risk"
    | "dramatization_risk"
    | "inner_state_overload"
    | "telling_over_action"
    | "subtext_missing"
    | "choice_missing"
    | "scene_mode_risk"
    | "sequel_mode_risk"
    | "mode_mixing_risk"
    | "no_turn_risk"
    | "prose_contract_violation"
    | "inner_state_budget_violation"
  severity: "low" | "medium" | "high"
  description: string
  suggested_fix?: string
  memory_refs?: SourceSpanRef[]
}
```

`risk_type` 的唯一内部白名单以 [../goals/26-agent-review-policy.md](../goals/26-agent-review-policy.md) 为准。本文只定义产品体验如何展示和处理这些风险，不维护第二套枚举。

边界：

- 可以影响候选排序和展示；
- 可以解释为什么某个候选风险更高；
- 可以帮助作者要求重写；
- 不能自动写入 Memory；
- 不能替代 SourceSpan；
- 不能直接阻塞作者采纳，除非产品明确要求二次确认；
- 不能在没有 SourceDelta / SourceSpan 的情况下升级为正式 `ReviewItem`。

## 3. ReviewItem

`ReviewItem` 是 Memory 层正式风险对象，由 Memory 的 conflict policy / review policy 产生。

```ts
type ReviewItem = {
  id: string
  source_span_refs: SourceSpanRef[]
  review_type:
    | "alias_conflict"
    | "event_merge_conflict"
    | "state_conflict"
    | "object_state_conflict"
    | "knowledge_conflict"
    | "pov_conflict"
    | "timeline_conflict"
    | "relationship_conflict"
    | "canon_conflict"
    | "version_conflict"
    | "source_scope_conflict"
    | "continuity_warning"
  severity: "low" | "medium" | "high"
  status: "open" | "dismissed" | "resolved" | "superseded"
  blocks_promotion: boolean
  description: string
  proposed_resolution?: string
}
```

只有在 Memory 回写阶段，且存在可追溯 `SourceSpan` 时，才应该生成正式 `ReviewItem`。

`review_type` 的唯一内部白名单以 [../goals/18-conflict-policy.md](../goals/18-conflict-policy.md) 为准。产品界面可以把这些类型翻译成更自然的写作语言。

## 4. 风险等级

| 等级 | 含义 | 默认处理 |
|---|---|---|
| low | 不太可能污染 canon，主要是提醒 | 轻提示，可自动继续 |
| medium | 可能影响角色认知、悬念状态或局部 canon | 进入可展开 Review，不阻塞写作 |
| high | 可能把未证实内容写成 canon，或造成严重连续性冲突 | 阻断 promotion，但不阻断正文继续写 |

## 5. 风险类型

### 5.1 POV / 角色认知风险

当前 POV 角色知道了不该知道的信息，或叙述越过当前视角。

例子：

```text
Mira 尚不知道钥匙来自敌人，但叙述直接写出“那把敌人给他的钥匙”。
```

对应内部类型：

- 草稿层：`pov_risk` / `knowledge_risk` / `forbidden_knowledge_leak` / `non_pov_mind_reading`
- Memory 层：`pov_conflict` / `knowledge_conflict`

### 5.2 过度推断 / 未证实内容

正文只提供暗示，但系统准备写成确定事实。

例子：

```text
正文：Kestrel 回避钥匙来源。
错误写入：Kestrel 背叛了 Mira。
```

对应内部类型：

- 草稿层：`unresolved_risk` / `canon_risk`
- Memory 层：通常映射为 `source_scope_conflict` / `canon_conflict` / `continuity_warning`

### 5.3 悬念误关闭 / 叙事债处理风险

正文保持悬念开放，但系统准备把线索结论化或关闭伏笔。

对应内部类型：

- 草稿层：`unresolved_risk` / `control_risk` / `no_turn_risk`
- Memory 层：通常映射为 `continuity_warning`

### 5.4 角色动机不一致

候选行为不符合当前角色欲望、恐惧、边界、压力或认知状态。

对应内部类型：

- 草稿层：`character_risk` / `agency_break_risk`
- Memory 层：通常不提升为正式 `ReviewItem`，除非接受后造成事实或连续性冲突

### 5.5 Canon 冲突

新正文与已确认 MemoryPage / Current Canon 冲突。

对应内部类型：

- 草稿层：`canon_risk` / `continuity_risk`
- Memory 层：`canon_conflict` / `state_conflict` / `timeline_conflict` / `object_state_conflict` / `relationship_conflict`

### 5.6 Alias / 事件合并风险

提及、别名或身份映射不确定，可能把两个角色、物品或身份错误合并。

对应内部类型：

- 草稿层：`unresolved_risk` / `continuity_risk`
- Memory 层：`alias_conflict` / `event_merge_conflict`

## 6. 非阻塞策略

风险处理不能让写作变成审批队列。

```mermaid
flowchart TD
    A[发现风险] --> B{风险来源}
    B -->|草稿候选| C[AgentReviewFinding]
    B -->|Memory 回写| D[ReviewItem]
    C --> E{作者是否采纳候选?}
    E -->|否| F[风险随候选关闭]
    E -->|是| G[SourceDelta / SourceSpan]
    G --> H[Memory Gate]
    H --> D
    D --> I{是否阻断 promotion?}
    I -->|是| J[不写入 Current Canon，进入 Review Queue]
    I -->|否| K[写入低风险 Memory，保留可撤销]
    J --> L[继续写作]
    K --> L
```

## 7. 产品行为要求

| 场景 | 产品行为 |
|---|---|
| 候选有低风险 | 在候选上轻提示，不打断选择 |
| 候选有中风险 | 展示原因和改写建议，允许继续采纳 |
| 候选有高风险 | 明确说明风险；允许作者 override，但 Memory 不自动 promote |
| Memory 回写有冲突 | 进入 Review Queue，不污染 Current Canon |
| 作者忽略风险 | 继续写作，风险保留为未处理状态 |
| 作者否定风险 | 标记 dismissed，并作为后续抽取纠错信号 |

## 8. 禁止行为

- 禁止把所有风险都弹窗化。
- 禁止因 ReviewItem 阻断正文保存。
- 禁止把 AgentReviewFinding 当作正式 Memory ReviewItem。
- 禁止把 high risk 候选采纳后直接 promote 到 Current Canon。
- 禁止把用户未处理风险视为用户确认。
- 禁止把 Review Queue 做成主界面默认负担。

## 9. 与用户心智的关系

面向作者的表达应尽量使用写作语言：

| 内部风险 | 面向作者表达 |
|---|---|
| pov_risk / knowledge_risk | 这里可能让角色知道了她不该知道的事 |
| unresolved_risk / canon_risk | 这里可能把暗示写得太实 |
| unresolved_risk / control_risk | 这里可能提前关闭一个悬念 |
| canon_conflict | 这里和之前确认的设定冲突 |
| alias_conflict | 这里可能把两个身份误认为同一个人 |
| character_risk / agency_break_risk | 这个行动可能不像该角色自然会做的事 |

产品默认应该帮助作者继续写，而不是迫使作者理解风险枚举。
