# 01. 总体数据流

> 本文档描述 Sextant 记忆系统从输入到输出的完整逻辑流。不讨论技术栈和实现细节。

## 1. 输入类型

| 输入 | 说明 | 主要输出 |
|---|---|---|
| 未完成手稿 | 作者自己的章节草稿、片段、续写 | RawSource、Chapter、Scene、MemoryPage |
| 授权原著 | 同人写作需要遵守的 canon source | Canon Memory、实体、事件、证据 |
| 设定集 | 世界观、历史、阵营、规则 | Lore、Location、Faction、Object |
| 角色卡 | 角色设定、关系、动机 | Character Memory |
| 作者笔记 | 灵感、未来计划、伏笔 | AuthorNote、OpenThread |
| 新写片段 | 作者刚写的一页或一场 | 增量更新、连续性检查、ContextPack |

## 2. 总体流程

```mermaid
flowchart TD
    A[Input Material\n手稿 / 原著 / 设定 / 角色卡] --> B[RawSource 保存]
    B --> C[SourceVersion\n版本与来源状态]
    C --> D[Chapter Parsing\n章节识别]
    D --> E[Scene Parsing\n场景识别]
    E --> F[SourceSpan\n证据片段]
    E --> G[ScenePOV\n视角判断]
    F --> H[Mention Extraction\n提及抽取]
    H --> I[Alias Registry\n别名归并]
    I --> J[CanonicalEntity\n稳定实体]
    E --> K[Event Extraction\n剧情事件]
    J --> L[FactAssertion\n事实断言]
    K --> L
    G --> M[CharacterKnowledge\n角色认知状态]
    L --> N[MemoryPage\nCurrent Canon]
    K --> N
    M --> N
    N --> O[GraphProjection\n故事图谱]
    N --> P[Retrieval\n问答 / 查设定]
    N --> Q[ContextPack\n续写上下文包]
    N --> R[ContinuityCheck\n一致性检查]
```

## 3. 标准 ingest 流程

```mermaid
sequenceDiagram
    participant User as 作者
    participant System as 记忆系统
    participant Source as RawSource
    participant Scene as Scene/Span
    participant Memory as MemoryPage
    participant Graph as GraphProjection

    User->>System: 导入手稿或原著
    System->>Source: 保存原文、来源、版本
    System->>Scene: 切分章节、场景、SourceSpan
    System->>Scene: 判断 POV 与场景状态
    System->>System: 抽取 Mention
    System->>System: 更新 AliasRegistry
    System->>Memory: 更新角色/地点/物品/事件记忆页
    System->>Graph: 重建故事图谱投影
    System-->>User: 返回可查询的故事记忆
```

## 4. 增量写作流程

作者不是一次性导入完整小说，而是一页一页写。

```mermaid
sequenceDiagram
    participant Author as 作者
    participant Memory as 记忆系统
    participant Check as 连续性检查
    participant Pack as ContextPack

    Author->>Memory: 提交新写片段
    Memory->>Memory: 解析场景、POV、SourceSpan
    Memory->>Memory: 更新 Mention、Event、Fact
    Memory->>Memory: 更新 Current Canon / Appearance Log
    Memory->>Check: 检查角色认知、时间线、物品状态、POV 漂移
    Check-->>Author: 返回风险提示
    Memory->>Pack: 生成下一页上下文包
    Pack-->>Author: 提供下一步写作记忆
```

## 5. 查询流程

```mermaid
flowchart LR
    A[作者问题] --> B[意图识别]
    B --> C{问题类型}
    C -->|查原文| D[SourceSpan Retrieval]
    C -->|查角色| E[MemoryPage Retrieval]
    C -->|查关系| F[GraphProjection Traversal]
    C -->|查矛盾| G[ContinuityCheck]
    C -->|续写| H[ContextPack Builder]
    D --> I[Evidence-backed Answer]
    E --> I
    F --> I
    G --> I
    H --> I
```

## 6. 输出类型

| 输出 | 用途 | 是否必须带证据 |
|---|---|---:|
| Evidence-backed Answer | 回答作者问题 | 是 |
| ContextPack | 给续写模型或作者使用的上下文 | 是 |
| MemoryPage | 角色、地点、事件等记忆页 | 是 |
| ContinuityWarning | 矛盾、视角漂移、角色认知错误 | 是 |
| OpenThread | 未解决伏笔、悬念、未来计划 | 建议 |
| AuthorNote | 作者手动设定或意图 | 是，来源为用户输入 |

## 7. 核心数据流判断

Sextant 不是：

```mermaid
flowchart LR
    A[原文] --> B[LLM 一步抽完整图谱] --> C[答案]
```

Sextant 是：

```mermaid
flowchart LR
    A[原文] --> B[证据] --> C[提及] --> D[实体/事件/事实] --> E[记忆页] --> F[图谱投影/检索] --> G[带证据答案]
```

