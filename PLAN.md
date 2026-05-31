# PLAN：Sextant Local-First MVP

本文件把现有宏观设计、工程实现规格和 web 工作台原型收敛成一个适合 Codex Goal mode 执行的 MVP 计划。

它不是完整生产实现排期，也不替代 `goals/`、`experience/` 或 `implementation/`。它只定义当前 long-horizon Goal 应该交付什么、如何验收、哪些不做。

## 1. 一句话 MVP

Sextant Local-First MVP 是一个面向小说作者的本地写作工作台：作者在当前章节中选中文本，请求候选续写，采纳一句候选后，系统把这次正文变化转成可追溯的 `AcceptedFragment -> SourceDelta -> SourceSpan -> MemoryWritebackPreview -> ReviewItem` 流程，并在刷新后保留状态。

## 2. 目标用户

主要用户：

- 正在写长篇小说、连载、同人或复杂世界观作品的作者；
- 需要 AI 帮忙继续局部段落，但不希望 AI 接管剧情方向；
- 关心 canon、角色认知、证据来源和长期记忆一致性。

用户场景：

- 作者正在编辑某一章或某一场景；
- 需要根据当前 POV、场景状态、已知/未知信息生成下一句或下一小段；
- 作者希望系统在采纳后帮忙记住相关事实、角色认知或开放悬念，但不要把未证实推断直接写成 canon。

## 3. 当前 Source Material

实现前必须读取：

- `AGENTS.md`
- `GOAL.md`
- `AGENT_GOAL.md`
- `experience/README.md`
- `experience/01-writing-session-loop.md`
- `experience/03-candidate-lifecycle.md`
- `experience/04-memory-writeback-contract.md`
- `experience/05-review-and-risk-contract.md`
- `implementation/README.md`
- `implementation/04-domain-state-machines.md`
- `implementation/09-frontend-integration.md`
- `implementation/13-acceptance-matrix.md`
- `web/` 当前原型代码；该目录在 PR #8 中引入。

## 4. Scope

### P0 — 必须完成

P0 目标是把现有静态工作台变成可运行、可验证、local-first 的垂直切片。

- [ ] App 可从 `web/` 安装、启动、lint、typecheck、build。
- [ ] 首页展示一个 demo project：章节、正文、当前 POV、场景卡、候选入口和 Review 状态。
- [ ] 用户能在正文中选中文本，并看到浮动操作菜单。
- [ ] 用户能从选区或 Ask 入口打开候选续写抽屉。
- [ ] 候选包含：候选方向、逐句候选、用到的 Memory、避开的未证实信息、风险提示。
- [ ] 用户能选择一句候选并加入正文。
- [ ] 加入正文时创建 `AcceptedFragment` domain object。
- [ ] 系统创建对应 `SourceDelta`，表示正文实际变化。
- [ ] 系统创建 mock/local `SourceSpan`，作为后续 Memory 证据锚点。
- [ ] 采纳后显示 `MemoryWritebackPreview`，列出待写入事实、角色认知、开放悬念或风险项。
- [ ] 用户可以确认低风险 writeback item。
- [ ] 用户可以撤销刚采纳的句子，并同时回退 writeback preview。
- [ ] 中/高风险或用户选择稍后处理的条目进入 Review Queue。
- [ ] 刷新页面后，正文变化、accepted fragments、source deltas、source spans、review queue 至少通过 `localStorage` 保留。
- [ ] 提供 reset demo state 的入口，便于重新演示和测试。
- [ ] P1/P2 按钮不能伪装为已完成：要么隐藏，要么禁用，要么明确标记为尚未实现。
- [ ] 不大改现有 UI 审美，只让现有交互闭环变真。

### P1 — P0 完成后再做

- [ ] 支持全文采纳候选。
- [ ] 支持替换当前句。
- [ ] 支持“借这个方向重写”。
- [ ] 支持查看候选依据的详细 SourceSpan 列表。
- [ ] 支持 Review Queue 的完整处理页。
- [ ] 支持导入一个本地 markdown 章节作为 demo source。
- [ ] 支持多 demo project 或多 chapter 切换。

### P2 — 明确非本轮目标

- [ ] 真实后端 API。
- [ ] Postgres persistence。
- [ ] 真实 LLM provider。
- [ ] 用户登录、权限、多租户。
- [ ] 生产部署。
- [ ] 完整 GraphProjection。
- [ ] 完整 Story Skill pipeline。
- [ ] 整章/整本自动写作。

## 5. Non-Goals

本轮 Goal 不做：

- 不重写产品哲学；
- 不改变 `goals/`、`experience/`、`implementation/` 的核心契约；
- 不把 DraftCandidate 直接写成 Memory 或 Canon；
- 不让 Agent 替作者决定剧情方向；
- 不接真实密钥或生产服务；
- 不引入复杂状态管理框架，除非现有 React state/localStorage 已明显无法支撑 P0；
- 不重做当前 web 工作台视觉风格。

## 6. Routes / Screens

| Route / Surface | 目的 | P0 状态 |
|---|---|---|
| `/` | 单页写作工作台 | required |
| Editor | 展示正文、处理选区、展示采纳后的文本 | required |
| Selection Menu | 从选区触发候选请求 | required |
| Ask Palette | 对话式入口，触发候选流程 | required |
| Candidate Drawer | 展示候选、依据、风险，允许选一句加入 | required |
| Memory Writeback | 展示“我准备记住这些”，允许确认/撤销/稍后处理 | required |
| Scene Card | 展示 POV、已知、未知、压力点、开放悬念 | required |
| Review Badge / Queue Summary | 展示待处理风险数量和简要条目 | required |
| Review Detail Page | 完整处理 ReviewItem | P1 |

## 7. Domain Objects for P0

P0 可以用 TypeScript domain types + local storage 实现，不需要后端。

```ts
type DemoProject = {
  id: string
  name: string
  chapter: string
  pov: string
  manuscript: ManuscriptParagraph[]
  sceneCard: SceneCard
}

type ManuscriptParagraph = {
  id: string
  text: string
  sourceSpanIds: string[]
}

type ActionRequest = {
  id: string
  kind: "ask_candidate" | "selection_candidate"
  selectedText?: string
  createdAt: string
}

type DraftCandidate = {
  id: string
  actionRequestId: string
  label: string
  direction: string
  sentences: CandidateSentence[]
  usedMemory: string[]
  avoidedClaims: string[]
  risk?: CandidateRisk
  status: "proposed" | "partially_accepted" | "discarded"
}

type AcceptedFragment = {
  id: string
  candidateId: string
  acceptedText: string
  acceptMode: "partial"
  targetParagraphId?: string
  createdAt: string
}

type SourceDelta = {
  id: string
  acceptedFragmentId: string
  deltaKind: "insert"
  insertedText: string
  createdAt: string
}

type SourceSpan = {
  id: string
  sourceDeltaId: string
  textPreview: string
  createdAt: string
}

type MemoryWritebackPreview = {
  id: string
  sourceSpanId: string
  items: WritebackItem[]
  status: "pending" | "resolved" | "undone"
}

type ReviewItem = {
  id: string
  sourceSpanId: string
  text: string
  hint: string
  level: "medium" | "high"
  status: "open" | "resolved" | "dismissed"
}
```

命名可以按实现需要微调，但不能破坏链条：

```text
DraftCandidate -> AcceptedFragment -> SourceDelta -> SourceSpan -> MemoryWritebackPreview -> ReviewItem
```

## 8. Persistence

P0 使用 `localStorage`。

建议 key：

```text
sextant.demo.v1
```

必须支持：

- 初次打开时加载 deterministic seed data；
- 采纳候选后保存状态；
- writeback 确认或撤销后保存状态；
- refresh 后恢复状态；
- reset demo state。

不得在 P0 中接入真实数据库、真实用户账户或真实模型供应商。

## 9. Mock Provider Policy

P0 使用 deterministic mock provider。

- 候选内容可以沿用当前 `web/lib/workbench-data.ts` 的候选方向和句子。
- mock provider 必须返回稳定数据，便于测试。
- mock 数据要逐步移动到 domain/provider 层，避免散落在 UI 组件里。
- 不使用真实 LLM，也不要求 API key。

## 10. Core User Flows

### Flow A：选中文本并打开候选

1. 用户打开工作台。
2. 用户在正文中选中一句或一段文字。
3. 系统显示 selection menu。
4. 用户点击候选动作。
5. 系统打开 Candidate Drawer。

验收：

- [ ] Candidate Drawer 可见。
- [ ] Drawer 显示至少 3 个候选方向。
- [ ] 每个候选展示 used memory / avoided claims / risk。

### Flow B：采纳一句候选并生成证据链

1. 用户在 Candidate Drawer 中选择一句候选。
2. 用户点击“选这句加入”。
3. 正文出现新增句子。
4. 系统创建 AcceptedFragment、SourceDelta、SourceSpan。
5. 系统打开 Memory Writeback。

验收：

- [ ] 正文展示新增句子。
- [ ] Domain state 中存在 accepted fragment。
- [ ] Domain state 中存在 source delta。
- [ ] Domain state 中存在 source span。
- [ ] Memory Writeback 显示待处理条目。

### Flow C：处理 Memory Writeback

1. 用户确认低风险条目。
2. 用户把中风险条目改弱或稍后处理。
3. 用户可撤销刚采纳的句子。
4. 中/高风险项可进入 Review Queue。

验收：

- [ ] 确认后条目从 pending list 移除。
- [ ] 撤销后新增正文和对应 writeback preview 被回退。
- [ ] Review badge 数量更新。
- [ ] 所有变化刷新后保留。

### Flow D：Reset Demo

1. 用户点击 reset demo state。
2. 系统恢复初始正文、候选、review 状态。

验收：

- [ ] localStorage 被清空或重建为 seed state。
- [ ] 页面恢复到初始 demo。

## 11. UI Direction

必须保留当前 web 工作台的设计审美：

- 安静、克制、以写作区为主角；
- 高信息密度但不压迫；
- 中文写作文案自然，不使用泛 SaaS 空话；
- Candidate Drawer、Memory Writeback、Scene Card 的现有层级和视觉语言尽量保留；
- 新增测试 selector、禁用状态、reset 入口时要轻量，不破坏布局。

## 12. Verification Commands

文档验证：

```bash
git diff --check -- AGENTS.md PLAN.md README.md docs implementation
```

前端验证：

```bash
pnpm --dir web install
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web build
```

P0 完成后应补充：

```bash
pnpm --dir web test
pnpm --dir web test:e2e
```

## 13. Milestones

### Milestone 1 — Goal-ready 文档

- [ ] `AGENTS.md`
- [ ] `PLAN.md`
- [ ] `README.md`
- [ ] `docs/goal-readiness-review.md`
- [ ] `docs/progress-log.md`
- [ ] `docs/known-gaps.md`
- [ ] `docs/implementation-decisions.md`

### Milestone 2 — 前端运行与验证脚本

- [ ] `web/README.md`
- [ ] `web/.env.example`
- [ ] `web/package.json` 增加 `typecheck`
- [ ] 记录当前缺少 test/e2e 的状态

### Milestone 3 — Domain / Store 垂直切片

- [ ] 定义 P0 domain types。
- [ ] 实现 deterministic seed state。
- [ ] 实现 localStorage store。
- [ ] 把采纳候选流程接到 domain state。

### Milestone 4 — UI 接入但不重设计

- [ ] 保留现有视觉风格。
- [ ] Editor 从 store 读取和展示正文。
- [ ] Candidate Drawer 使用 mock provider。
- [ ] Memory Writeback 处理真实 preview state。
- [ ] Review badge 读取真实 review queue。
- [ ] P1 按钮隐藏/禁用/标记。

### Milestone 5 — 测试与验收

- [ ] Unit tests 覆盖 domain transitions。
- [ ] Playwright 覆盖核心 flow。
- [ ] README 更新运行和验收说明。
- [ ] `docs/progress-log.md` 和 `docs/known-gaps.md` 更新。

## 14. Completion Criteria

本 MVP 完成必须同时满足：

- [ ] P0 全部完成。
- [ ] 现有 UI 审美未被大改。
- [ ] 前端能安装、启动、lint、typecheck、build。
- [ ] 如果已添加 unit/e2e 测试，测试通过。
- [ ] 刷新页面后核心状态保留。
- [ ] Reset demo 可用。
- [ ] 所有 P1/P2 未实现入口不伪装成完成。
- [ ] `docs/progress-log.md` 有最终记录。
- [ ] `docs/known-gaps.md` 记录非阻塞缺口。

## 15. Known Risks

- 现有 web 工作台是高质量视觉原型，但 domain state 仍偏 mock，需要小心迁移，避免把 UI 重写成普通 SaaS dashboard。
- 文档体系很完整，Codex 可能过度实现生产架构；本轮必须收窄到 local-first MVP。
- `implementation/` 规划的是生产系统，P0 只能做前端本地垂直切片，不应引入后端复杂度。
- 如果测试依赖一次性加入太多，可能拖慢 PR；可以先加 typecheck/build，再补 unit/e2e。
