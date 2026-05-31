# Implementation Decisions

本文记录实现过程中做出的关键取舍，尤其是 Codex Goal mode 可能需要复用的决策。

## 2026-05-31 — 将当前 long-horizon 目标收窄为 local-first MVP

### Decision

当前不直接实现完整生产系统，而是先实现 `PLAN.md` 中定义的 local-first P0 垂直切片。

### Reason

`goals/`、`experience/`、`implementation/` 已经定义了完整系统的产品和工程边界，但直接把它们作为一次 Goal 的实现范围过大。Codex Goal mode 更适合有明确验收面的目标。

### Consequence

P0 只做：

```text
selection -> candidate -> accepted fragment -> source delta -> source span -> memory writeback preview -> review queue
```

不做真实后端、Postgres、真实 LLM、登录、多租户或生产部署。

## 2026-05-31 — 保留现有 web 工作台审美

### Decision

后续 web 改动必须保留 PR #8 中现有工作台的视觉方向，不进行大规模 redesign。

### Reason

当前 UI 已经符合 Sextant 的产品气质：安静、克制、写作区优先、高信息密度但不压迫。P0 的主要缺口是 domain/store/persistence/test，不是视觉重做。

### Consequence

允许：

- 接入 domain/store；
- 增加 localStorage persistence；
- 增加测试 selector；
- 轻量增加 reset demo；
- 禁用或标记 P1 按钮。

不允许：

- 改成通用 SaaS dashboard；
- 大改布局密度；
- 重做字体、颜色、卡片语言；
- 为了测试方便破坏写作工作台气质。

## 2026-05-31 — P0 默认使用 deterministic mock provider

### Decision

P0 不接真实 LLM provider，使用 deterministic mock provider。

### Reason

P0 的目标是把采纳和记忆回写链条做成可验证产品闭环。真实模型会引入密钥、网络、响应不稳定和评测复杂度，反而削弱 Goal mode 的可验证性。

### Consequence

- 不需要真实 API key。
- `web/.env.example` 只声明 mock mode。
- 候选内容可以从当前 demo data 迁移到 mock provider。
- 后续真实 LLM 接入作为 P2 / 生产实现处理。

## 2026-05-31 — P0 使用 localStorage persistence

### Decision

P0 使用 `localStorage` 存储 demo state。

### Reason

它足以验证刷新保留状态、撤销、Review Queue 和 domain transition，不需要引入后端。

### Consequence

建议 key：

```text
sextant.demo.v1
```

后续生产实现再迁移到 API + Postgres。

## 2026-05-31 — 文档 PR 与 web PR 分工

### Decision

文档类改动进入 PR #7，web 代码和配置进入 PR #8。

### Reason

当前 PR stack 已经明确：#7 是工程实现技术设计文档，#8 是 web 工作台原型。

### Consequence

- `AGENTS.md`、`PLAN.md`、`README.md`、`docs/*` 进入 #7。
- `web/README.md`、`web/.env.example`、`web/package.json` 脚本补齐进入 #8。
