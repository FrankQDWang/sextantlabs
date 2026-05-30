# 06. 对话式入口契约

> 本文档定义对话式 Agent 在 Sextant 中的位置：它是入口和解释层，不是产品主体。本文不定义聊天 UI 样式。

## 1. 核心判断

Sextant 需要自然语言入口，但不应该把产品变成聊天机器人。

作者经常会用自然语言表达写作意图：

```text
帮我查一下 Mira 现在知不知道钥匙来源。
让 Kestrel 更可疑，但不要坐实。
这段太直白了，压一点。
检查这段有没有穿帮。
为什么你建议让他沉默？
```

这些输入应该被解析成结构化写作动作，而不是进入开放式聊天漂移。

```text
Natural Language
  ↓
Intent Parse
  ↓
ActionRequest
  ↓
Story Skill / Agent
  ↓
MemoryAnswer / DraftCandidate / AgentReviewFinding / CandidateExplanation
```

## 2. 对话式入口的职责

对话式入口负责：

- 查询 Memory；
- 解释候选依据；
- 改写作者意图；
- 澄清方向；
- 处理风险；
- 把自然语言转成结构化 ActionRequest。

它不负责：

- 作为默认写作界面；
- 直接覆盖正文；
- 直接写入 Memory；
- 直接决定 canon；
- 替代候选采纳流程；
- 替代 Review Policy；
- 让用户在聊天历史里管理小说项目。

## 3. 输入到 ActionRequest 的映射

| 作者表达 | ActionRequest | 输出 |
|---|---|---|
| 她现在知道钥匙是谁给的吗？ | ask_memory | MemoryAnswer |
| 让 Kestrel 更可疑，但不要坐实 | rewrite_span / revise_candidate | DraftCandidate |
| 这段有没有 POV 穿帮？ | check_risk | AgentReviewFinding[] |
| 下面可以发生什么？ | suggest_next_direction | BeatCandidate[] |
| 把这句写得更克制 | rewrite_span | DraftCandidate[] |
| 为什么这个候选合理？ | explain_candidate | CandidateExplanation |
| 别关闭钥匙来源这个悬念 | revise_candidate with keep_thread_open | DraftCandidate[] |

## 4. Memory 问答契约

自然语言问答必须返回可验证结果，而不是自由聊天回答。

```ts
type MemoryAnswer = {
  id: string
  question: string
  answer: string
  answer_type: "canon" | "pov_knowledge" | "open_thread" | "unknown" | "conflict"
  source_span_refs: SourceSpanRef[]
  unknowns?: string[]
  related_review_items?: string[]
  safe_to_use_in_current_pov: boolean
}
```

回答必须区分：

| answer_type | 含义 |
|---|---|
| canon | Current Canon 中已确认的事实 |
| pov_knowledge | 当前 POV 角色知道、怀疑、误解或不知道的内容 |
| open_thread | 悬念、伏笔或未解决问题 |
| unknown | Memory 没有足够证据回答 |
| conflict | 存在冲突或待审核信息 |

## 5. 候选解释契约

对话式入口可以解释候选，但解释不能成为 canon 证据。

```ts
type CandidateExplanation = {
  candidate_id: string
  why_this: string
  used_memory_refs: SourceSpanRef[]
  respected_constraints: string[]
  avoided_claims: string[]
  risks: AgentReviewFinding[]
}
```

解释应该回答：

- 使用了哪些 Memory；
- 避开了哪些未证实事实；
- 保持了哪些悬念开放；
- 当前 POV 是否能知道这些信息；
- 如果采纳，可能产生哪些 Memory 回写。

## 6. 澄清契约

如果自然语言意图不明确，系统可以追问，但追问应该是结构化选择，而不是开放聊天。

例子：

```text
你想让 Kestrel 更可疑，是想：
1. 增加 Mira 的怀疑；
2. 增加读者的怀疑；
3. 让 Kestrel 做一个含糊动作；
4. 让某个证据指向他，但不坐实。
```

追问结果应回填到 `ActionRequest.constraints`，而不是只留在聊天记录中。

## 7. 风险处理契约

对话式入口可以帮助作者处理风险：

- 解释风险为什么存在；
- 把候选改得更弱；
- 把确定事实改成角色怀疑；
- 保持悬念开放；
- 将风险延后处理；
- 标记作者否定。

但它不能直接关闭正式 `ReviewItem`，除非作者明确做出对应操作，并且该操作被记录为结构化决定。

```ts
type ReviewDecision = {
  review_item_id: string
  decision: "accept" | "dismiss" | "weaken" | "defer" | "supersede"
  author_note?: string
}
```

## 8. 位置原则

最终 UI 可以有自然语言入口，但默认不应把它做成常驻主界面。

推荐的产品位置是：

- 全局命令入口，用于 Ask / 查记忆 / 查风险；
- 选中文本后的上下文动作；
- 候选上的解释、重写和约束操作；
- Memory 或 Review 卡片上的追问入口。

这些入口都应该通向 `ActionRequest`，而不是通向无限聊天。

## 9. 禁止行为

- 禁止把聊天记录当成项目状态源。
- 禁止聊天回答直接写入正文。
- 禁止聊天回答直接写入 Memory。
- 禁止在聊天中隐藏 canon promotion。
- 禁止让作者通过闲聊间接确认高风险事实。
- 禁止把开放式对话作为所有功能的唯一入口。
- 禁止让对话式 Agent 绕过 Story Skill 和 Memory Gate。

## 10. 总结

对话式 Agent 在 Sextant 中的正确位置是：

```text
自然语言入口 + 意图澄清 + 证据解释 + 风险处理辅助
```

而不是：

```text
聊天窗口 + 自由生成 + 直接写正文 + 直接污染 Memory
```

产品层必须把自然语言转成结构化写作动作。