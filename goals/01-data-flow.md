# 01. 总体数据流

> 本文档描述 Sextant 记忆系统从输入到输出的 **唯一主流程**。它与 [GOAL.md](../GOAL.md) 中的 canonical end-to-end flow 同构。本文不讨论技术栈和实现细节。

## 1. 输入类型

| 输入 | 说明 | 主要进入路径 |
|---|---|---|
| 未完成手稿 | 作者自己的章节草稿、片段、续写 | RawSource -> ProcessedMarkdownView -> Memory |
| 授权原著 | 同人写作需要遵守的 canon source | RawSource -> external canon memory |
| 设定集 | 世界观、历史、阵营、规则 | RawSource -> Lore / Faction / Location Memory |
| 角色卡 | 角色设定、关系、动机 | RawSource -> Character Memory |
| 作者笔记 | 灵感、未来计划、伏笔 | RawSource -> Author Note / OpenThread |
| 新写片段 | 作者刚写的一页或一场 | SourceDelta -> 增量回写 |
| 模型建议 | AI 给出的候选文本或建议 | 低权重材料，不自动进入 canon |

## 2. Canonical End-to-End Flow

```mermaid
flowchart TD
    A[Raw Source\n手稿 / 原著 / 设定 / 角色卡] --> B[Source Preservation\n保存原文、来源、版本]
    B --> C[Source Normalization\nProcessedMarkdownView]
    C --> D[Structure Parsing\nChapter / Scene / SourceSpan]
    D --> E[POV & Scene Memory\n视角、场景摘要、场景状态]
    E --> F[Mention Extraction\n原始提及]
    F --> G[Alias Registry\n非阻塞别名归并]
    G --> H[CanonicalEntity\n稳定故事实体]
    E --> I[EventCandidate Extraction\n剧情事件候选]
    I --> J[Event Aggregation\nCanonicalEvent]
    H --> K[FactAssertion\n带证据事实断言]
    J --> K
    K --> L[Evidence / Log Writeback\nAppearance Log / Event Log / Source refs]
    K --> M[Conflict Policy Gate\n风险检查]
    M -->|通过| N[Canon Promotion\n允许改写 Current Canon]
    M -->|中高风险| O[ReviewItem\n保留证据但不自动升格]
    L --> P[MemoryPage\n日志、证据、开放问题]
    N --> P
    P --> Q[Story Auto-Link\n确定性边生成]
    Q --> R[GraphProjection\n可重建故事图谱]
    P --> S[Retrieval / ContextPack\n问答、续写上下文、查矛盾]
    R --> S
    O --> S
```

关键约束：

| 约束 | 含义 |
|---|---|
| Raw Source 先保存 | 冲突、低置信、格式问题都不能阻断原始材料保存 |
| Evidence / Log 可先写 | 新证据可以先进入日志，不等于 Current Canon 被改写 |
| Current Canon 有 gate | 任何高风险事实、别名、状态变化必须经过 Conflict Policy Gate |
| GraphProjection 可重建 | 图谱不是事实源，只是投影 |
| ContextPack 按需生成 | 增量回写只更新它的依赖，不默认每次生成完整 ContextPack |

## 3. 标准 ingest 流程

```mermaid
sequenceDiagram
    participant User as 作者
    participant Source as RawSource
    participant View as ProcessedMarkdownView
    participant Structure as Structure Parsing
    participant Extract as Mention / Event Extraction
    participant Gate as Conflict Policy Gate
    participant Page as MemoryPage
    participant Graph as GraphProjection

    User->>Source: 导入手稿、原著或设定材料
    Source->>View: 生成规范化 Markdown View
    View->>Structure: 解析 Chapter / Scene / SourceSpan
    Structure->>Extract: 抽取 Mention 与 EventCandidate
    Extract->>Gate: 生成 FactAssertion 并检查风险
    Gate-->>Page: 低风险事实进入 Current Canon
    Gate-->>Page: 所有证据进入 Log / Source refs
    Gate-->>User: 中高风险生成 ReviewItem
    Page->>Graph: Story Auto-Link 后重建图谱投影
```

## 4. 增量写作流程

作者不是一次性导入完整小说，而是一页一页写。增量流程仍沿用 canonical flow，只是局部执行。

```mermaid
sequenceDiagram
    participant Author as 作者
    participant Delta as SourceDelta
    participant Log as Evidence / Log
    participant Gate as Conflict Policy Gate
    participant Canon as Current Canon
    participant Review as ReviewItem
    participant Pack as ContextPack Builder

    Author->>Delta: 提交新写片段
    Delta->>Log: 保存 SourceSpan、Mention、EventCandidate、FactAssertion
    Delta->>Gate: 检查别名、时间线、POV、物品状态、知识状态
    Gate-->>Canon: 低风险或已接受事实才改写 Current Canon
    Gate-->>Review: 中高风险生成 ReviewItem
    Canon->>Pack: 标记续写上下文依赖已更新
    Review->>Pack: 标记上下文生成时应携带未处理风险
```

注意：新增正文后不默认生成完整 ContextPack。系统只更新 ContextPack 所依赖的 MemoryPage、GraphProjection、ReviewItem。用户请求续写或问答时，才按需生成 ContextPack。

## 5. 查询与 ContextPack 流程

```mermaid
flowchart LR
    A[作者问题或续写请求] --> B[意图识别]
    B --> C{问题类型}
    C -->|查原文| D[SourceSpan Retrieval]
    C -->|查角色/设定| E[MemoryPage Retrieval]
    C -->|查关系/事件| F[GraphProjection Traversal]
    C -->|查矛盾| G[ReviewItem / Continuity Risk]
    C -->|续写| H[ContextPack Builder]
    D --> I[Evidence-backed Answer]
    E --> I
    F --> I
    G --> I
    H --> I
```

## 6. 输出类型

| 输出 | 用途 | 是否必须带证据 | 默认生成时机 |
|---|---|---:|---|
| Evidence-backed Answer | 回答作者问题 | 是 | 用户查询时 |
| ContextPack | 给续写模型或作者使用的上下文 | 是 | 用户请求续写时按需生成 |
| MemoryPage | 角色、地点、事件等记忆页 | 是 | ingest / 增量回写后更新 |
| ReviewItem | 冲突、别名、连续性风险 | 是 | Conflict Policy Gate 产生 |
| OpenThread | 未解决伏笔、悬念、未来计划 | 建议 | 回写或检查时产生 |
| AuthorNote | 作者手动设定或意图 | 是，来源为用户输入 | 用户输入时 |

## 7. 核心数据流判断

Sextant 不是：

```mermaid
flowchart LR
    A[原文] --> B[LLM 一步抽完整图谱] --> C[答案]
```

Sextant 是：

```mermaid
flowchart LR
    A[原文] --> B[ProcessedMarkdownView] --> C[SourceSpan] --> D[Mention / EventCandidate] --> E[Entity / CanonicalEvent / FactAssertion] --> F[Conflict Gate] --> G[MemoryPage] --> H[GraphProjection / ContextPack] --> I[带证据答案]
```
