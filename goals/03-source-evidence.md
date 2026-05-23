# 03. 原始材料与证据系统

> 原始材料和证据系统是 Sextant 的根。所有记忆、回答、续写上下文都必须能回到原文。

## 1. RawSource 的角色

RawSource 是输入材料本身，不是系统总结。

```mermaid
flowchart TD
    A[RawSource] --> B[SourceVersion]
    B --> C[Chapter]
    C --> D[Scene]
    D --> E[SourceSpan]
    E --> F[Mention]
    E --> G[FactAssertion]
    E --> H[EventEntity]
    E --> I[Answer Citation]
```

RawSource 可以是：

| 类型 | 例子 | 主要用途 |
|---|---|---|
| manuscript | 作者未完成手稿 | 建立当前作品 canon |
| canon | 授权原著或同人参考材料 | 建立外部 canon |
| character_sheet | 角色卡 | 角色基础设定 |
| worldbuilding | 世界观文档 | 地点、阵营、规则、历史 |
| author_note | 作者笔记 | 未来意图、伏笔、修改计划 |
| discarded_draft | 废弃草稿 | 作为历史，不直接进入当前 canon |

## 2. SourceVersion

小说写作中，同一章会反复修改。记忆系统必须区分版本。

| 状态 | 含义 |
|---|---|
| active | 当前有效版本 |
| previous | 历史版本 |
| discarded | 废弃版本 |
| experimental | 实验性片段 |
| canon_reference | 原著或授权 canon 来源 |

版本变化不应直接删除旧证据，而应改变其 canon 状态。

```mermaid
stateDiagram-v2
    [*] --> active
    active --> previous: 新版本替换
    active --> discarded: 作者废弃
    active --> experimental: 标记为实验
    previous --> active: 回滚
    discarded --> active: 恢复
```

## 3. SourceSpan

SourceSpan 是最小证据单位。

一个 SourceSpan 应该足够短，能精准指向原文；又要足够长，能让人理解上下文。

| 用途 | SourceSpan 的作用 |
|---|---|
| 回答作者问题 | 提供引用依据 |
| 抽取 Mention | 标记提及出现位置 |
| 抽取 Event | 标记事件发生位置 |
| 事实断言 | 证明这个事实来自哪里 |
| 连续性检查 | 说明矛盾来自哪些段落 |
| 续写上下文 | 给模型必要证据而不是整章全文 |

## 4. 证据链

任何回答都应形成证据链。

```mermaid
flowchart LR
    A[作者问题] --> B[检索 MemoryPage / Graph / Span]
    B --> C[找到 FactAssertion]
    C --> D[追溯 SourceSpan]
    D --> E[生成答案]
    E --> F[附带证据引用]
```

## 5. 原文、摘要和记忆的区别

| 层级 | 是否原文 | 是否可修改 | 用途 |
|---|---:|---:|---|
| RawSource | 是 | 不建议直接修改 | 原始证据 |
| SourceSpan | 是 | 不建议直接修改 | 精准引用 |
| Scene Summary | 否 | 可重写 | 便于理解场景 |
| FactAssertion | 否 | 可更正 | 事实记忆 |
| MemoryPage | 否 | 可重写 | 当前 canon 综合 |
| ContextPack | 否 | 临时生成 | 续写/问答 |

## 6. 证据状态

| 状态 | 含义 |
|---|---|
| current_canon | 当前有效 canon 的证据 |
| prior_version | 历史版本证据 |
| discarded | 已废弃设定，仅作历史 |
| author_intent | 作者笔记，代表意图而非成稿事实 |
| external_canon | 外部原著或参考 canon |
| model_inferred | 模型推断，必须可被作者覆盖 |

## 7. 证据系统的边界

不允许：

- 模型总结替代原文证据；
- 无 SourceSpan 的事实直接进入 canon；
- 废弃草稿继续影响续写上下文；
- 把角色误解当成世界真实事实；
- 把同人外部 canon 和作者当前作品 canon 混成一层。

