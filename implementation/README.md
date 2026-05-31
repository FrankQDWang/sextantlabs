# Sextant 工程实现规格

`implementation/` 是 Sextant 的工程实现 source-of-truth。它和 `goals/`、`experience/` 同级，不是普通补充说明。

本文档集的目标不是定义 MVP，而是把 `goals/` 中完整的 Memory、Agent、Storytelling Control 设计转成可生产实现的工程边界、数据契约、测试门和 PR 拆分。

## Source-of-Truth 顺序

当文档冲突时，按以下顺序处理：

1. `goals/`：领域对象、Memory、Agent、Storytelling Control 的产品和领域逻辑。
2. `experience/`：用户动作、写作会话、候选、回写、风险展示的产品契约。
3. `implementation/`：工程实现边界、schema、API、测试、CI/CD、部署与运维。
4. `backend/`、`web/`：实现代码。代码不能重新定义上层契约。
5. Planning 文档：只能安排实施顺序，不能改写契约。

## 文档索引

| 文档 | 作用 |
|---|---|
| [00-overview.md](00-overview.md) | 总体架构、技术栈、硬边界、质量门总览 |
| [01-source-of-truth-map.md](01-source-of-truth-map.md) | `goals/` 和 `experience/` 到工程规格的覆盖映射 |
| [02-module-boundaries.md](02-module-boundaries.md) | Python modular monolith 的包边界、导入规则和代码所有权 |
| [03-persistence-schema.md](03-persistence-schema.md) | Postgres 表、约束、索引、migration 和事务边界 |
| [04-domain-state-machines.md](04-domain-state-machines.md) | Candidate、SourceDelta、ReviewItem、Fact、Job 等状态机 |
| [05-application-use-cases.md](05-application-use-cases.md) | Application layer use case、事务、幂等和错误边界 |
| [06-story-skills-and-llm-harness.md](06-story-skills-and-llm-harness.md) | Story Skill 协议、LLM harness、prompt 版本和 golden tests |
| [07-agent-and-storytelling-control.md](07-agent-and-storytelling-control.md) | Next Page Agent、Storytelling Control、ProseRenderingContract 工程化 |
| [08-api-contracts.md](08-api-contracts.md) | HTTP API、DTO、OpenAPI、错误码和客户端生成 |
| [09-frontend-integration.md](09-frontend-integration.md) | Vite + React 工作台和后端契约的集成边界 |
| [10-worker-and-jobs.md](10-worker-and-jobs.md) | DB-backed worker、job、retry、幂等和后台管线 |
| [11-ci-cd-and-ai-guardrails.md](11-ci-cd-and-ai-guardrails.md) | CI/CD、tach、ty、ruff、semgrep、PR 模板和 AI coding 围栏 |
| [12-observability-security-ops.md](12-observability-security-ops.md) | 审计、日志、隐私、安全、部署和生产运维 |
| [13-acceptance-matrix.md](13-acceptance-matrix.md) | 生产实现验收矩阵、测试映射和 Definition of Done |
| [14-implementation-pr-stack.md](14-implementation-pr-stack.md) | 建议 PR 栈、依赖关系和每层交付物 |

## 不可压缩链条

实现必须保留以下链条：

```text
ActionRequest
  -> WritingContextPack / Story Skill / Agent
  -> BeatCandidate / DraftCandidate / MemoryAnswer / AgentReviewFinding
  -> AcceptedFragment
  -> SourceDelta
  -> RawSource / SourceVersion / ProcessedMarkdownView
  -> SourceSpan
  -> Mention / EventCandidate / FactAssertion / CharacterKnowledge
  -> EvidenceLogEntry
  -> Conflict Policy Gate
  -> Canon Promotion / ReviewItem
  -> MemoryPage / GraphProjection / ContextPackReadiness
```

任何实现、prompt、agent、API、前端动作或 worker job 都不能把这条链条压缩成捷径。

## 生产实现最低标准

一个实现 PR 只有同时满足以下条件，才算进入可合并状态：

1. 契约覆盖：能指出它实现了 `goals/`、`experience/`、`implementation/` 中哪些条款。
2. 边界受控：tach、semgrep 或测试能阻止最关键的越界路径。
3. 数据可追溯：写入 Memory、Canon、Review 的对象能回到 SourceSpan 或明确用户输入。
4. 测试明确：至少有 unit 或 contract test；涉及 skill/prompt 的必须有 golden test。
5. 迁移可执行：任何 schema 变更必须有 Alembic migration，并在 CI 中 upgrade。
6. 前端不造 schema：前端使用生成 API client，不维护第二套领域模型。
7. 审计可解释：关键 LLM、promotion、review、writeback 决策有 audit record。

## 非目标

- 不把 `implementation/` 当任务排期。
- 不在这里定义 UI 视觉稿。
- 不让 GraphProjection、ContextPack 或 MemoryPage 覆盖底层证据。
- 不允许“先实现再补契约”。
