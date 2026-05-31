# 02. ActionRequest 契约

> 本文档定义作者的自然语言、按钮点击和选中文本如何转成结构化写作动作。它不定义 UI 组件形态，也不绑定具体实现。

## 1. 为什么需要 ActionRequest

对话式 Agent 可以存在，但不能成为产品主体。

作者可以用自然语言表达意图，例如：

```text
让 Kestrel 更可疑，但不要坐实。
这段太直白了，压一点。
她现在知道钥匙是谁给的吗？
检查这段有没有 POV 穿帮。
```

产品层不能把这些话直接丢进一个开放聊天回合，而应先转成 `ActionRequest`。

```text
自然语言 / 选中文本 / 点击动作
  ↓
ActionRequest
  ↓
Story Skill / Agent
  ↓
Memory Answer / BeatCandidate / DraftCandidate / AgentReviewFinding
```

## 2. ActionRequest 的职责

`ActionRequest` 只描述作者要系统做什么，以及当前动作作用于哪里。

它不负责：

- 直接生成正文；
- 直接写入 Memory；
- 决定 canon；
- 跳过 ContextPack；
- 跳过作者采纳。

## 3. 基础结构

```ts
type ActionRequest = {
  id: string
  project_id: string
  source_id?: string
  source_version_id?: string
  scene_id?: string
  chapter_id?: string
  pov_character_id?: string
  actor_intent: string
  trigger: ActionTrigger
  action_type: ActionType
  target?: ActionTarget
  constraints?: ActionConstraint[]
  expected_output: ExpectedOutput
}
```

## 4. 触发来源

```ts
type ActionTrigger =
  | "natural_language"
  | "selected_text"
  | "toolbar_action"
  | "candidate_action"
  | "memory_card_action"
  | "review_card_action"
```

含义：

| trigger | 含义 |
|---|---|
| natural_language | 作者通过 Ask / 命令入口表达意图 |
| selected_text | 作者选中正文或候选的一部分 |
| toolbar_action | 作者点击结构化动作，如查前文、查风险 |
| candidate_action | 作者对某个候选要求解释、重写、局部采纳 |
| memory_card_action | 作者基于 Memory 卡片发起追问或纠错 |
| review_card_action | 作者处理风险或确认冲突 |

## 5. 动作类型

第一阶段只保留和写作闭环直接相关的动作。

```ts
type ActionType =
  | "ask_memory"
  | "check_risk"
  | "suggest_next_direction"
  | "rewrite_span"
  | "render_current_beat"
  | "continue_small_passage"
  | "explain_candidate"
  | "revise_candidate"
```

| action_type | 输出 | 是否可直接进入正文 |
|---|---|---:|
| ask_memory | MemoryAnswer | 否 |
| check_risk | AgentReviewFinding[] | 否 |
| suggest_next_direction | BeatCandidate[] | 否 |
| rewrite_span | DraftCandidate[] | 否，必须作者采纳 |
| render_current_beat | DraftCandidate[] | 否，必须作者采纳 |
| continue_small_passage | DraftCandidate[] | 否，必须作者采纳 |
| explain_candidate | CandidateExplanation | 否 |
| revise_candidate | DraftCandidate[] | 否，必须作者采纳 |

## 6. 目标范围

```ts
type ActionTarget =
  | { kind: "cursor_position"; source_id: string; offset: number }
  | { kind: "source_span"; source_span_id: string }
  | { kind: "selected_text"; source_id: string; range: { start: number; end: number } }
  | { kind: "candidate"; candidate_id: string }
  | { kind: "scene"; scene_id: string }
  | { kind: "memory_page"; memory_page_id: string }
  | { kind: "review_item"; review_item_id: string }
```

所有写作类动作都必须有明确目标范围，不能对整个项目自由生成。

## 7. 约束

```ts
type ActionConstraint =
  | { kind: "do_not_confirm_fact"; description: string }
  | { kind: "keep_thread_open"; thread_id?: string; description: string }
  | { kind: "pov_limited"; character_id: string }
  | { kind: "tone"; value: string }
  | { kind: "length"; value: "sentence" | "short_paragraph" | "page" }
  | { kind: "avoid_canon_promotion"; description: string }
```

例子：

```text
“让 Kestrel 更可疑，但不要坐实”
```

应转成：

```ts
{
  action_type: "rewrite_span",
  actor_intent: "make Kestrel feel more suspicious without confirming betrayal",
  constraints: [
    { kind: "do_not_confirm_fact", description: "Kestrel betrayed Mira" },
    { kind: "keep_thread_open", description: "key origin remains unresolved" },
    { kind: "pov_limited", character_id: "Mira" }
  ],
  expected_output: "draft_candidates"
}
```

## 8. 输出类型

```ts
type ExpectedOutput =
  | "memory_answer"
  | "risk_findings"
  | "beat_candidates"
  | "draft_candidates"
  | "candidate_explanation"
```

输出类型决定产品如何处理结果：

- `memory_answer` 显示答案、证据和未知点；
- `risk_findings` 显示风险，但不修改正文；
- `beat_candidates` 是方向，不是正文；
- `draft_candidates` 是候选文本，必须经作者采纳；
- `candidate_explanation` 解释候选依据，不写入 Memory。

## 9. 禁止行为

- 禁止将自然语言请求直接变成正文写入。
- 禁止绕过 ActionRequest 直接调用写作 Agent。
- 禁止没有 target 的大范围续写。
- 禁止 `DraftCandidate` 在未采纳时进入 Memory。
- 禁止把 `actor_intent` 当成 canon 事实。
- 禁止用候选解释反向证明候选内容已经成立。