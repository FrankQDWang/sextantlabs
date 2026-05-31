# Known Gaps

本文记录当前仓库相对于 `PLAN.md` P0 MVP 和后续生产实现仍缺少的内容。

## 1. P0 阻塞缺口

这些缺口会阻塞 local-first MVP 完成。

### 1.1 Domain / Store 层尚未实现

当前 `web/` 工作台仍主要使用组件 state 和 mock data。P0 需要补：

- `DemoProject`
- `ActionRequest`
- `DraftCandidate`
- `AcceptedFragment`
- `SourceDelta`
- `SourceSpan`
- `MemoryWritebackPreview`
- `ReviewItem`

并把核心交互接入这些 domain object。

### 1.2 localStorage persistence 尚未实现

P0 要求刷新后保留：

- 正文新增句子；
- accepted fragments；
- source deltas；
- source spans；
- writeback preview 状态；
- review queue。

建议 key：

```text
sextant.demo.v1
```

### 1.3 采纳链条仍未真实落地

必须保留并实现：

```text
DraftCandidate -> AcceptedFragment -> SourceDelta -> SourceSpan -> MemoryWritebackPreview -> ReviewItem
```

目前 UI 已经能演示“选一句加入”和“我准备记住这些”，但它还不是完整 domain transition。

### 1.4 P1 按钮需要处理

当前 web 原型中存在一些尚未完整实现的动作，例如：

- 替换当前句；
- 借这个方向重写；
- 查看依据；
- 全文采纳。

P0 中不能让这些按钮伪装为已完成。需要选择一种处理方式：

- 隐藏；
- 禁用；
- 标记为 P1 / soon；
- 或真正实现并加入测试。

### 1.5 测试缺失

P0 完成前应补：

- domain transition unit tests；
- Playwright e2e 主流程：选中文本 -> 打开候选 -> 选一句加入 -> memory writeback -> confirm/review -> refresh persistence；
- reset demo state 测试。

## 2. P0 非阻塞但建议尽快补的内容

### 2.1 CI workflow

建议在 P0 或下一轮 PR 增加：

```bash
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web test
pnpm --dir web build
pnpm --dir web test:e2e
```

### 2.2 稳定测试 selector

Playwright 前应为关键入口增加稳定 selector，例如：

- editor root；
- selection action；
- candidate drawer；
- accept sentence button；
- memory writeback panel；
- review badge；
- reset demo state。

这些 selector 不应改变视觉审美。

### 2.3 Error / Empty states

P0 可以先用 demo seed data，但最好补轻量状态：

- seed load failed；
- localStorage parse failed；
- reset state；
- no candidate available。

## 3. P1 缺口

这些不阻塞 P0。

- 全文采纳候选。
- 替换当前句。
- 借方向重写。
- 查看候选依据的完整 SourceSpan 列表。
- Review Queue 详情页。
- 本地 markdown 导入。
- 多项目或多章节切换。
- 更完整的 Undo history。

## 4. P2 / 生产级缺口

这些属于 `implementation/` 描述的生产级实现，不属于当前 P0。

- 后端 API。
- Postgres persistence。
- Alembic migration。
- 真实 LLM provider。
- Story Skill pipeline。
- Worker / jobs。
- GraphProjection。
- ContextPack readiness。
- 用户认证。
- 多租户。
- 部署和 observability。
- 安全扫描和生产 smoke test。

## 5. 不应作为缺口处理的内容

以下不是当前 P0 的缺口，不应诱导 Codex 扩 scope：

- 自动生成整章或整本小说；
- 自动替作者决定剧情；
- 完整 GraphRAG；
- 纯向量记忆；
- 一步抽完整知识图谱；
- 把模型输出直接写入 Current Canon；
- 大改当前 web UI 审美。

## 6. 当前状态摘要

```text
Goal-ready docs: done in PR #7
Web runbook/typecheck: to be added in PR #8
Local-first MVP implementation: not started
Tests/e2e: not started
Production backend: out of P0 scope
```
