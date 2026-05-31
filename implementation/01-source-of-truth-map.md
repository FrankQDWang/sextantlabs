# 01. Source-of-Truth 覆盖映射

本文档说明现有产品、Memory、Agent 和 Storytelling Control 设计如何落到工程实现规格。它的作用是防止后续 Codex 实现时只读某一个总览文档，而漏掉 `goals/` 中的完整设计。

## 覆盖规则

1. 每个 `goals/*.md` 都必须至少被一个 `implementation/*.md` 承接。
2. 每个新增领域枚举必须能回到 `goals/` 或本目录中的明确白名单。
3. `experience/` 可以定义用户动作和展示语义，但不能维护第二套领域枚举。
4. 如果实现发现 `goals/` 和 `implementation/` 冲突，先更新设计文档或 ADR，再写代码。

## Memory 核心设计映射

| 源文档 | 工程落点 | 必须实现的最小边界 |
|---|---|---|
| `goals/00-design-principles.md` | `00-overview.md`, `13-acceptance-matrix.md` | Evidence-first、Mention-first、Canon over Truth 成为测试和 guardrail |
| `goals/01-data-flow.md` | `05-application-use-cases.md`, `10-worker-and-jobs.md` | canonical flow 必须由 use case 和 job 串联，不允许旁路 |
| `goals/02-core-data-structures.md` | `03-persistence-schema.md`, `04-domain-state-machines.md` | 核心对象、枚举、source-of-truth 顺序落到 domain + schema |
| `goals/03-source-evidence.md` | `03-persistence-schema.md`, `12-observability-security-ops.md` | RawSource、SourceVersion、SourceSpan 是证据根 |
| `goals/04-scenes-pov.md` | `03-persistence-schema.md`, `06-story-skills-and-llm-harness.md` | Chapter、Scene、POV、CharacterKnowledge 具备 schema 和抽取 skill |
| `goals/05-mentions-aliases.md` | `03-persistence-schema.md`, `06-story-skills-and-llm-harness.md` | Mention-first、AliasRecord 状态、用户纠错路径 |
| `goals/06-entities-events-facts.md` | `03-persistence-schema.md`, `04-domain-state-machines.md` | Entity/Event/Fact 分层，不允许直接抽自由图 |
| `goals/07-memory-pages.md` | `03-persistence-schema.md`, `05-application-use-cases.md` | MemoryPage 是综合记忆，不替代 EvidenceLogEntry |
| `goals/08-graph-projection.md` | `03-persistence-schema.md`, `05-application-use-cases.md` | GraphProjection 可重建，只能从结构化对象投影 |
| `goals/09-retrieval-context-pack.md` | `05-application-use-cases.md`, `08-api-contracts.md` | Evidence-backed Answer 与 ContextPack 必须区分 canon/risk |
| `goals/10-continuity-check.md` | `06-story-skills-and-llm-harness.md`, `04-domain-state-machines.md` | ContinuityWarning 统一为 ReviewItem |
| `goals/11-non-goals.md` | `00-overview.md`, `13-acceptance-matrix.md` | 明确不做全自动不可逆归并、纯向量记忆和 GraphRAG 主系统 |
| `goals/12-inspirations.md` | `00-overview.md` | 外部启发只作为取舍背景，不变成实现依赖 |

## Schema、Skill、回写映射

| 源文档 | 工程落点 | 必须实现的最小边界 |
|---|---|---|
| `goals/13-skills-and-resolver.md` | `06-story-skills-and-llm-harness.md`, `10-worker-and-jobs.md` | thin harness + fat story skills，skill 不能直接 commit DB |
| `goals/14-story-schema-packs.md` | `03-persistence-schema.md`, `06-story-skills-and-llm-harness.md` | Base schema、Genre Pack、Project Overrides 有版本化存储 |
| `goals/15-event-aggregation.md` | `06-story-skills-and-llm-harness.md`, `03-persistence-schema.md` | EventCandidate -> CanonicalEvent -> FactAssertion 不能跳过 gate |
| `goals/16-source-normalization.md` | `06-story-skills-and-llm-harness.md`, `03-persistence-schema.md` | ProcessedMarkdownView 可重建，必须保存 raw offset map ref |
| `goals/17-incremental-memory-writeback.md` | `05-application-use-cases.md`, `10-worker-and-jobs.md` | SourceDelta 触发局部回写，不全量重写所有 MemoryPage |
| `goals/18-conflict-policy.md` | `04-domain-state-machines.md`, `05-application-use-cases.md` | Conflict Policy Gate 只阻断 promotion，不阻断 ingest |
| `goals/19-story-auto-link.md` | `05-application-use-cases.md`, `03-persistence-schema.md` | Auto-Link 从结构化记忆对象投影，不直接读 RawSource 建图 |

## Agent 与 Storytelling Control 映射

| 源文档 | 工程落点 | 必须实现的最小边界 |
|---|---|---|
| `goals/20-agent-overview.md` | `07-agent-and-storytelling-control.md`, `08-api-contracts.md` | Agent proposes, Author accepts, Memory records |
| `goals/21-writing-context-pack.md` | `05-application-use-cases.md`, `07-agent-and-storytelling-control.md` | WritingContextPack 明确 canon、risk、POV、style 分层 |
| `goals/22-character-agency-profile.md` | `07-agent-and-storytelling-control.md`, `03-persistence-schema.md` | Character Agency Profile 是行为模型，不是事实源 |
| `goals/23-next-page-agent.md` | `07-agent-and-storytelling-control.md`, `08-api-contracts.md` | Suggest、Draft、Rewrite 三种模式都返回候选，不写正文 |
| `goals/24-draft-candidate-lifecycle.md` | `04-domain-state-machines.md`, `05-application-use-cases.md` | Candidate 状态机采用 `generated/reviewed/offered_to_author/...` |
| `goals/25-agent-memory-writeback.md` | `05-application-use-cases.md`, `10-worker-and-jobs.md` | Accepted text 和作者手写文本走同一 Memory flow |
| `goals/26-agent-review-policy.md` | `04-domain-state-machines.md`, `07-agent-and-storytelling-control.md` | AgentReviewFinding 与 ReviewItem 严格分层 |
| `goals/27-storytelling-control-layer.md` | `07-agent-and-storytelling-control.md` | Storytelling Control 只产控制对象，不产正文，不写 Memory |
| `goals/28-role-need-and-cast-expansion.md` | `07-agent-and-storytelling-control.md` | RoleSlot 与 CharacterCastingDecision 是草稿层控制产物 |
| `goals/29-new-character-policy.md` | `07-agent-and-storytelling-control.md`, `03-persistence-schema.md` | NewCharacterSeed 接受后才进入 Memory ingest |
| `goals/30-dramatization-layer.md` | `07-agent-and-storytelling-control.md` | 内心状态转成动作、台词、沉默、物体和选择 |
| `goals/31-inner-state-rendering.md` | `07-agent-and-storytelling-control.md` | 非 POV 内心不能直接进入 prose |
| `goals/32-scene-sequel-mode.md` | `07-agent-and-storytelling-control.md` | Scene/Sequel/Mixed 模式成为 ProseRenderingContract 输入 |
| `goals/33-prose-rendering-contract.md` | `07-agent-and-storytelling-control.md`, `06-story-skills-and-llm-harness.md` | ProseRenderingContract 是最终写作模型输入边界 |

## 产品体验映射

| 源文档 | 工程落点 | 必须实现的最小边界 |
|---|---|---|
| `experience/00-product-principles.md` | `09-frontend-integration.md`, `13-acceptance-matrix.md` | Editor first、Candidate not manuscript、Non-blocking review |
| `experience/01-writing-session-loop.md` | `05-application-use-cases.md`, `09-frontend-integration.md` | 写作会话闭环能解释每次采纳和每次回写 |
| `experience/02-action-request-contract.md` | `08-api-contracts.md`, `05-application-use-cases.md` | 自然语言、按钮、选区都先变成 ActionRequest |
| `experience/03-candidate-lifecycle.md` | `04-domain-state-machines.md`, `09-frontend-integration.md` | UI 状态映射到 canonical Candidate 状态机 |
| `experience/04-memory-writeback-contract.md` | `05-application-use-cases.md`, `09-frontend-integration.md` | MemoryWritebackPreview 是轻量安全阀，不是阻断弹窗 |
| `experience/05-review-and-risk-contract.md` | `04-domain-state-machines.md`, `09-frontend-integration.md` | AgentReviewFinding 和 ReviewItem 的展示和处理分层 |
| `experience/06-conversational-entry-contract.md` | `08-api-contracts.md`, `09-frontend-integration.md` | 对话入口只能转 ActionRequest，不能自由写正文或 Memory |

## 验收规则

每个实现 PR 必须在 PR body 中写明：

```text
Implemented source docs:
- goals/...
- experience/...
- implementation/...

Protected boundaries:
- ...

Tests:
- ...
```

如果无法指出源文档，说明该 PR 不是当前产品/工程设计的一部分，应先补设计或删除实现。
