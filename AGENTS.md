# AGENTS.md

本文件是给 Codex / AI coding agent 的仓库操作手册。它不替代产品设计文档，只定义：在这个仓库里如何读上下文、如何实施、如何验证、如何停止。

## 1. 当前仓库状态

Sextant 当前处在“宏观设计 → 工程实现 → web 工作台原型 → MVP”的过渡期。

当前 open PR stack：

1. `docs/technical-implementation-design`：工程实现规格文档。
2. `codex/web-workbench-on-implementation`：叠在上一个分支上的 `web/` 工作台原型。

修改放置规则：

- 纯文档、Goal-ready 计划、验收标准、实施决策：放在 `docs/technical-implementation-design`。
- 涉及 `web/` 的工程配置、测试、前端代码：放在 `codex/web-workbench-on-implementation`。
- 不要为了实现功能而大改现有前端视觉审美。当前工作台 UI 的审美方向应被保留。

## 2. Source-of-Truth 顺序

发生冲突时，按以下顺序处理：

1. `goals/`：领域对象、Memory、Agent、Storytelling Control 的产品和领域逻辑。
2. `experience/`：用户动作、写作会话、候选、回写、风险展示的产品契约。
3. `implementation/`：工程实现边界、schema、API、测试、CI/CD、部署与运维。
4. `PLAN.md`：当前 Codex Goal/MVP 的执行范围和验收标准。
5. `web/`、未来 `backend/`：实现代码。
6. `docs/progress-log.md`、`docs/known-gaps.md`：过程记录和剩余缺口。

`PLAN.md` 可以收窄实现范围，但不能改写上层契约。代码不能重新定义上层契约。

## 3. Repo Layout

- `GOAL.md`：Sextant Memory 系统宏观目标。
- `AGENT_GOAL.md`：Sextant 写作 Agent 宏观目标。
- `goals/`：Memory、Agent、Storytelling Control 的领域设计。
- `experience/`：产品体验契约。
- `implementation/`：生产级工程实现规格。
- `PLAN.md`：当前 local-first MVP 的可执行计划。
- `docs/`：Goal readiness、实施决策、进度和缺口。
- `web/`：Vite + React 写作工作台原型。该目录在 PR #8 中引入。

## 4. Working Directory 与包管理器

前端工作目录：

```bash
cd web
```

前端包管理器：

```bash
pnpm
```

如果本地没有启用 Corepack：

```bash
corepack enable
```

## 5. 常用命令

### 文档检查

```bash
git diff --check -- AGENTS.md PLAN.md README.md docs implementation
rg -n "TODO|TBD|[ \t]+$" AGENTS.md PLAN.md README.md docs implementation || true
```

### 前端安装与运行

```bash
pnpm --dir web install
pnpm --dir web dev
```

### 前端验证

```bash
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web build
```

如果后续添加 unit/e2e 测试，应补齐并使用：

```bash
pnpm --dir web test
pnpm --dir web test:e2e
```

## 6. Goal Mode 工作规则

长程 Goal 开始前必须先读：

1. `AGENTS.md`
2. `PLAN.md`
3. `GOAL.md`
4. `AGENT_GOAL.md`
5. `experience/README.md`
6. `implementation/README.md`
7. 与任务直接相关的 `goals/*`、`experience/*`、`implementation/*`

执行方式：

- 先确认当前任务属于文档 PR 还是前端 PR。
- 先做垂直切片，不要横向铺开大量未接通代码。
- 每完成一个 checkpoint，更新 `docs/progress-log.md`。
- 所有未完成但不阻塞 P0 的内容，写入 `docs/known-gaps.md`。
- 如果发现上层契约冲突，不要静默选择；记录到 `docs/implementation-decisions.md`。
- 如果 blocked，停止并报告：blocker、证据、尝试过的路径、继续所需输入。

## 7. 前端实现约束

现有 `web/` 工作台 UI 审美方向是可保留资产。除非用户明确要求，不要大改：

- 整体布局密度；
- 字体层级；
- 克制、安静的写作工作台气质；
- Candidate Drawer、Memory Writeback、Scene Card 的视觉语言；
- 中文文案风格。

允许的前端改动：

- 把 demo state 移入 domain/store 层；
- 增加 local-first persistence；
- 增加测试所需的稳定 selector；
- 隐藏、禁用或标记尚未实现的 P1 按钮；
- 修复 lint/typecheck/build 问题；
- 改善可访问性和响应式，但不得重做视觉风格。

## 8. Domain Boundary

实现时必须保留以下链条，不能走捷径：

```text
DraftCandidate
  -> AcceptedFragment
  -> SourceDelta
  -> SourceSpan
  -> MemoryWritebackPreview
  -> ProposedMemory / ReviewItem
  -> MemoryPage / Review Queue
```

禁止：

```text
DraftCandidate -> MemoryPage
DraftCandidate -> Current Canon
AgentReviewFinding -> ReviewItem without SourceSpan
模型推断 -> CanonFact without evidence
```

## 9. Dependency Policy

- 默认不添加生产依赖。
- 添加依赖前必须说明原因，并记录到 `docs/implementation-decisions.md`。
- 测试依赖可以加入，但要同步更新 package lock 和 README。
- 不提交真实 secret、API key、用户私有文本或生产凭据。
- P0 默认使用 mock provider，不依赖真实 LLM。

## 10. Definition of Done

一个 Goal/MVP 实现任务完成必须满足：

- P0 acceptance criteria in `PLAN.md` 全部完成，或剩余项有明确 blocker 证据。
- 文档和代码没有重新定义上层契约。
- 前端视觉审美没有被无关重写。
- `pnpm --dir web lint` 通过。
- `pnpm --dir web typecheck` 通过。
- `pnpm --dir web build` 通过。
- 如果已添加测试：`pnpm --dir web test`、`pnpm --dir web test:e2e` 通过。
- `docs/progress-log.md` 有最终记录。
- `docs/known-gaps.md` 列出非阻塞缺口。

## 11. Recommended Goal Prompt

```text
/goal Implement the P0 MVP described in PLAN.md.

Read AGENTS.md first. Treat GOAL.md, AGENT_GOAL.md, goals/, experience/, and implementation/ as source material, but use PLAN.md as the implementation scope for this run.

Preserve the current web workbench visual direction. Do not redesign the UI. Build a local-first, mock-provider MVP that makes the existing writing workflow real: selection -> candidate -> accepted fragment -> source delta -> source span -> memory writeback preview -> review queue.

Update docs/progress-log.md after each checkpoint and docs/known-gaps.md for non-blocking gaps. Stop only when P0 acceptance criteria and verification commands pass, or when blocked with exact evidence.
```
