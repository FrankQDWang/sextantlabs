# Sextant 产品体验契约

> 本目录只定义 **产品体验边界、用户动作到系统对象的契约、写作会话闭环、候选生命周期、记忆回写和风险处理**。
>
> 本目录不定义最终 UI 稿、不提交 wireframe、不提交 HTML、不规定视觉风格、不讨论技术栈、数据库、模型选型或实现代码。最终界面设计交给独立 UI 设计流程处理。

## 1. 定位

Sextant 的产品体验不是“聊天生成小说”，也不是“AI IDE”。

它应该保持以下闭环：

```text
作者正在写
  ↓
自然语言意图 / 选中文本 / 点击动作
  ↓
ActionRequest 结构化写作动作
  ↓
ContextPack 当前写作上下文
  ↓
Story Skill / Agent 生成候选、解释或风险发现
  ↓
作者局部采纳 / 全文采纳 / 忽略 / 重写
  ↓
被采纳内容成为 SourceDelta
  ↓
SourceSpan 形成证据锚点
  ↓
Memory 分层回写：事实、角色认知、开放悬念、ReviewItem
  ↓
继续写作
```

产品层必须保护一个硬边界：

```text
DraftCandidate ≠ Manuscript Text ≠ SourceDelta ≠ SourceSpan ≠ Memory ≠ Canon
```

候选文本只有在作者采纳后才进入正文。正文变化只有形成 SourceSpan 后，才可作为 Memory 证据。Memory 仍需区分 Current Canon、角色认知、开放悬念和待审核风险。

## 2. 文档索引

| 文档 | 作用 |
|---|---|
| [00-product-principles.md](00-product-principles.md) | 产品体验原则和不可破坏边界 |
| [01-writing-session-loop.md](01-writing-session-loop.md) | 一次写作会话从打开章节到 Memory 回写的完整闭环 |
| [02-action-request-contract.md](02-action-request-contract.md) | 自然语言、按钮和选区如何变成结构化 ActionRequest |
| [03-candidate-lifecycle.md](03-candidate-lifecycle.md) | DraftCandidate 到 AcceptedFragment、SourceDelta、Memory 的状态边界 |
| [04-memory-writeback-contract.md](04-memory-writeback-contract.md) | “准备记住这些”的数据契约和分层回写策略 |
| [05-review-and-risk-contract.md](05-review-and-risk-contract.md) | AgentReviewFinding、ReviewItem、风险等级和非阻塞处理 |
| [06-conversational-entry-contract.md](06-conversational-entry-contract.md) | 对话式 Agent 作为入口，而不是产品主体 |

## 3. 不在本目录解决的问题

- 最终 UI layout；
- 组件视觉样式；
- 颜色、字体、间距、图标；
- 响应式断点；
- 具体前端框架；
- 后端 API 实现；
- 数据库存储结构；
- 模型或 harness 选型；
- 一次性替作者生成整章或整本小说。

本目录的目标是先确认：用户动作是什么，系统对象如何变化，什么内容能进入 Memory，什么内容必须停在 Review。