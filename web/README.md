# Sextant Web Workbench

这是 Sextant 的 Vite + React 写作工作台原型。当前目标是保留现有 UI 审美，并逐步把 mock/demo 交互补成 local-first MVP。

## 运行

```bash
pnpm install
pnpm dev
```

或从仓库根目录运行：

```bash
pnpm --dir web install
pnpm --dir web dev
```

## 验证

```bash
pnpm lint
pnpm typecheck
pnpm build
```

或从仓库根目录运行：

```bash
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web build
```

当前还没有 unit/e2e 测试。P0 MVP 完成前应补：

```bash
pnpm test
pnpm test:e2e
```

## Demo 操作

当前工作台展示一个固定 demo project：`Harbor Nine · Ch.03 西档案室 · POV Mira`。

可试用的交互：

1. 在正文中选中任意文字。
2. 点击浮动菜单打开候选续写。
3. 在 Candidate Drawer 中选择一句候选。
4. 点击“选这句加入”。
5. 查看右下角“我准备记住这些”面板。
6. 处理或关闭 writeback 条目。
7. 使用底部状态切换器浏览演示状态。
8. 按 `Cmd/Ctrl + K` 打开 Ask Palette。

## 当前状态

当前 web 原型已经具备：

- editor；
- selection menu；
- ask palette；
- candidate drawer；
- memory writeback panel；
- scene card；
- review badge；
- deterministic mock data。

但它还不是完整 P0 MVP。下一步需要补：

- domain/store 层；
- localStorage persistence；
- `AcceptedFragment -> SourceDelta -> SourceSpan` 链条；
- real writeback preview state；
- review queue state；
- reset demo state；
- unit tests；
- Playwright e2e。

## UI 约束

当前工作台的视觉方向应保留：

- 写作区是主角；
- 整体安静、克制；
- 信息密度高但不压迫；
- 中文文案保持自然；
- Candidate Drawer、Memory Writeback、Scene Card 的视觉语言不要大改。

允许的改动：

- 接入 domain/store；
- 接入 localStorage；
- 增加测试 selector；
- 增加 reset demo 入口；
- 禁用或标记 P1 按钮；
- 修复 lint/typecheck/build。

不建议的改动：

- 重做整体 layout；
- 改成通用 SaaS dashboard；
- 大改颜色、字体、密度或组件语气；
- 为了测试方便破坏现有写作体验。

## 环境变量

P0 默认使用 mock provider，不需要真实 API key。参考 `web/.env.example`。
