# Codex Goal Readiness Review

本文记录当前仓库为了运行 Codex Goal mode long-horizon 任务还缺什么、已经补了什么、下一步应该怎么补。

## 1. 总体判断

当前仓库已经具备很强的产品和领域设计基础，但在本次补齐前还不是一个可以直接交给 Codex Goal mode 长程实现产品的任务包。

原因不是产品方向不清楚，而是缺少以下执行层材料：

- agent 操作手册；
- 当前 MVP 的 P0/P1/P2 范围；
- 可运行命令和验证命令；
- progress log 与 known gaps；
- web 原型的 runbook；
- local-first MVP 的验收标准；
- test/e2e 的引入计划。

本轮已在 PR #7 补齐文档层，PR #8 负责补齐 web 层的轻量运行说明和验证脚本。

## 2. 已满足的部分

### 2.1 产品方向清楚

`GOAL.md` 已经定义 Sextant 是面向小说作者的外部长期记忆系统，核心是把作者自己的手稿、授权原著、设定集、角色卡、章节草稿等材料转化为可追溯、可检索、可校正、可用于续写上下文的故事记忆。

### 2.2 Agent 边界清楚

`AGENT_GOAL.md` 已经定义 Agent 是基于记忆、由角色驱动、逐页推进的写作副驾驶，不是自动写完整小说的 autopilot。

核心边界是：

```text
Agent proposes.
Author accepts.
Memory records.
```

### 2.3 产品体验闭环清楚

`experience/` 已经定义：

```text
作者正在写
  -> ActionRequest
  -> ContextPack
  -> Story Skill / Agent
  -> 候选、解释或风险
  -> 作者采纳
  -> SourceDelta
  -> SourceSpan
  -> Memory 回写
  -> 继续写作
```

并且明确：

```text
DraftCandidate != Manuscript Text != SourceDelta != SourceSpan != Memory != Canon
```

### 2.4 生产工程规格已经开始形成

PR #7 的 `implementation/` 已经定义生产系统的模块边界、schema、状态机、API、worker、CI/CD、验收矩阵等。

### 2.5 web 原型已经存在

PR #8 的 `web/` 已经提供 Vite + React 工作台原型，包括：

- editor；
- candidate drawer；
- memory writeback；
- review badge；
- selection menu；
- top bar；
- scene card；
- mock demo data。

## 3. 已补齐的 Goal-ready 文档

本轮在 PR #7 新增：

- `AGENTS.md`：Codex / AI coding agent 操作手册。
- `PLAN.md`：local-first MVP 的 P0/P1/P2、验收标准和里程碑。
- `README.md`：仓库入口和当前 PR stack 说明。
- `docs/goal-readiness-review.md`：本文件。
- `docs/progress-log.md`：长程 Goal 过程记录。
- `docs/known-gaps.md`：非阻塞缺口和后续工作。
- `docs/implementation-decisions.md`：实施决策记录。

## 4. 仍需在 PR #8 补齐的 web 层内容

PR #8 应补：

- `web/README.md`：前端运行、验证、demo 操作说明。
- `web/.env.example`：明确 P0 默认 mock provider，无真实密钥。
- `web/package.json`：增加 `typecheck` script。

PR #8 可以暂不立刻加入 unit/e2e 依赖，但必须在 `docs/known-gaps.md` 记录。P0 真正实现时，应补 `test` 和 `test:e2e`。

## 5. 当前缺口分级

### Blocking for full Goal implementation

- `web/` 仍是 demo/mock state，没有 domain/store 层。
- 没有 localStorage persistence。
- 没有 AcceptedFragment / SourceDelta / SourceSpan 的真实 domain object。
- 没有 unit/e2e 测试。
- 没有 CI workflow。

### Not blocking for Goal-ready documentation

- 没有后端。
- 没有真实 LLM provider。
- 没有 Postgres。
- 没有登录和多租户。
- 没有生产部署。

这些都是 P2，不应阻塞当前 local-first MVP。

## 6. 推荐执行顺序

1. 合并 PR #7：工程规格 + Goal-ready 文档。
2. 合并 PR #8：web 工作台原型 + web runbook + typecheck。
3. 新开 P0 implementation PR：实现 local-first domain/store/persistence。
4. 新开 tests PR：补 unit tests 和 Playwright e2e。
5. 再考虑后端、真实 LLM、Postgres、CI/CD。

## 7. 推荐 Goal Prompt

```text
/goal Implement the P0 MVP described in PLAN.md.

Read AGENTS.md first. Preserve the current web workbench visual direction. Do not redesign the UI. Build a local-first, mock-provider vertical slice: selection -> candidate -> accepted fragment -> source delta -> source span -> memory writeback preview -> review queue.

Update docs/progress-log.md after each checkpoint and docs/known-gaps.md for non-blocking gaps. Stop only when P0 acceptance criteria and verification commands pass, or when blocked with exact evidence.
```

## 8. Readiness Status

After this documentation pass, the repository should be considered:

```text
Goal-ready for planning and P0 implementation.
Not yet complete as a usable product.
```

The next implementation goal should be scoped to `PLAN.md` P0, not to the entire production system described in `implementation/`.
