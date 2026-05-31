# 00. 产品体验原则

> 本文档定义 Sextant 的产品体验原则。它不是 UI 稿，不规定视觉布局，不包含 wireframe。

## 1. 产品定位

Sextant 是一个以正文编辑器为中心、以候选为辅助、以证据记忆为底座的小说写作工作台。

它不是：

- 聊天写作器；
- 自动替作者写完整小说的 autopilot；
- AI IDE；
- 数据库管理面板；
- 图谱编辑器；
- 大纲生成器。

Sextant 的核心体验应该是：

```text
作者保持在写作现场
AI 提供候选、解释、查证和风险提示
作者决定是否采纳
Memory 只记录有证据的变化
不确定内容进入 Review，而不是污染 canon
```

## 2. 核心原则

| 原则 | 产品含义 |
|---|---|
| Editor first | 正文创作是主场景；所有辅助能力都服务当前写作位置。 |
| Structured actions over chat | 自然语言可以作为入口，但必须被转成结构化写作动作。 |
| Candidate, not manuscript | AI 输出默认是候选，不是正文。 |
| Partial accept by default | 产品应鼓励作者拿一句、一个动作或一个方向，而不是整段吞下。 |
| Evidence before memory | 没有 SourceSpan 的内容不能成为正式 Memory 证据。 |
| Canon is gated | 正文接受不等于 canon；canon promotion 必须经过证据和风险判断。 |
| Non-blocking review | 风险提示帮助作者，但不阻断写作。 |
| Memory on demand | Memory 以当前写作需要出现，不以数据库管理界面出现。 |
| Low cognitive load | 面向有想法但缺写作训练的作者，避免暴露内部术语。 |
| Thin harness, rich skills | 产品动作应路由到明确 Story Skill，而不是堆成一个万能聊天框。 |

## 3. 硬边界

产品和系统必须共同保护以下边界：

```text
DraftCandidate ≠ Manuscript Text
Manuscript Text change ≠ Canon
AcceptedFragment → SourceDelta → SourceSpan → MemoryExtraction → Promotion / Review
```

含义：

1. Agent 生成的 `DraftCandidate` 不能直接写入正文。
2. 作者采纳后才产生 `AcceptedFragment`。
3. 正文变化产生 `SourceDelta`。
4. `SourceDelta` 必须建立 `SourceSpan` 后，才能成为后续 Memory 的证据。
5. Memory 抽取结果先是 proposed memory，不自动等于 Current Canon。
6. 不确定、冲突、过度推断、POV 风险必须进入 Review。

## 4. 产品语言与内部对象

产品界面不应该强迫作者理解内部对象名。内部对象可以保持严谨，但对作者展示时应翻译成写作语言。

| 内部对象 | 面向作者的表达 |
|---|---|
| FactAssertion | 我准备记住一个故事事实 |
| CharacterKnowledgeState | 这个角色现在知道 / 怀疑 / 误解什么 |
| NarrativeDebt | 开放悬念 / 未回收伏笔 / 当前问题 |
| ReviewItem | 这里可能穿帮 / 需要你稍后决定 |
| SourceSpan | 证据来自这段正文 |
| ContextPack | 当前写作上下文 |
| DraftCandidate | 候选句 / 候选动作 / 候选方向 |

## 5. 默认体验应该避免什么

- 避免常驻大型聊天窗口成为主界面。
- 避免把实体表、关系表、图谱节点直接暴露给作者。
- 避免把每次 Memory 回写都做成强制确认弹窗。
- 避免让“全文采纳”成为默认主动作。
- 避免让风险提示打断写作流。
- 避免让模型草稿反过来证明自己的 canon。
- 避免把角色认知、作者 canon、读者认知和模型推测混成一层。

## 6. 当前阶段的设计目标

当前阶段不是产出最终 UI，而是确认产品契约：

```text
用户看见什么类型的状态
用户可以做什么动作
动作如何变成系统对象
哪些对象可以写入 Memory
哪些对象必须停在 Review
哪些内部机制不能出现在默认体验中
```

视觉设计、交互细节、组件样式和响应式布局交给后续 UI 设计流程。