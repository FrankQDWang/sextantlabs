# Sextant Labs

Sextant 是面向小说作者的外部长期记忆系统。它的目标不是替作者接管创作，而是在作者写作时提供可追溯、可校正、POV-aware 的故事记忆和局部续写辅助。

## 当前内容

仓库目前分为几层：

- `goals/`：Memory、Agent、Storytelling Control 的领域设计。
- `experience/`：写作会话、候选生命周期、记忆回写和风险处理的产品体验契约。
- `implementation/`：生产级工程实现规格，在 PR #7 中新增。
- `web/`：Vite + React 写作工作台原型，在 PR #8 中新增。

## 当前 PR Stack

- PR #7 `docs/technical-implementation-design`：工程实现规格和 Goal-ready 文档。
- PR #8 `codex/web-workbench-on-implementation`：叠在 #7 上的 web 工作台原型。

修改放置原则：

- 文档、计划、验收标准和 Codex Goal 准备：放到 #7。
- 涉及 `web/` 的代码、脚本、测试和前端说明：放到 #8。
- 不要为了补工程能力而大改当前 web 原型的审美方向。

## 给 Codex / AI Coding Agent 的入口

先读：

1. `AGENTS.md`
2. `PLAN.md`
3. `GOAL.md`
4. `AGENT_GOAL.md`
5. `experience/README.md`
6. `implementation/README.md`

`AGENTS.md` 是操作手册，`PLAN.md` 是当前 local-first MVP 的执行范围。

## 文档结构

```text
GOAL.md             # Sextant Memory 宏观目标
AGENT_GOAL.md       # Sextant Agent 宏观目标
goals/              # Memory / Agent / Storytelling Control 领域设计
experience/         # 产品体验契约
implementation/     # 生产级工程实现规格
PLAN.md             # 当前 Codex Goal / MVP 计划
AGENTS.md           # Codex 操作手册
docs/               # readiness review、进度、缺口、实施决策
web/                # 前端工作台原型，位于 PR #8
```

## 前端运行

`web/` 目录在 PR #8 中引入。切到包含 #8 的分支后：

```bash
pnpm --dir web install
pnpm --dir web dev
```

前端验证：

```bash
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web build
```

后续 P0 完成后应补齐：

```bash
pnpm --dir web test
pnpm --dir web test:e2e
```

## 当前 MVP 方向

当前最合适的 long-horizon Goal 是先把现有 web 工作台做成 local-first 的 P0 垂直切片：

```text
selection -> candidate -> accepted fragment -> source delta -> source span -> memory writeback preview -> review queue
```

完整范围见 `PLAN.md`。

## 文档验证

```bash
git diff --check -- AGENTS.md PLAN.md README.md docs implementation
```

## 当前限制

- `web/` 当前仍以 mock/demo 数据为主。
- P0 计划要求 localStorage persistence，但尚未实现。
- 后端、Postgres、真实 LLM、认证、多租户、生产部署均不属于当前 P0。
- UI 审美方向应保留，不做大改。
