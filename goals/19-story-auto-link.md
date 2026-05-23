# 19. Story Auto-Link 与确定性建图

> 本文档定义 Sextant 如何借鉴确定性 auto-link 思路，把规范化记忆页、frontmatter、场景出场、事件结构和已确认别名投影为稳定故事图谱。这里不讨论实现，只讨论数据流和规则边界。

本文对应 [GOAL.md](../GOAL.md) 中 canonical end-to-end flow 的 `Memory Pages` -> `Story Auto-Link` -> `Graph Projection` 片段。Story Auto-Link 只消费已经结构化的 MemoryPage、Scene、Event、Fact、AliasRegistry 和 CharacterKnowledge，不从 RawSource 直接建图。

## 1. 核心目标

Story Auto-Link 的目标不是从原始正文里直接理解整本小说，而是从已经结构化的记忆对象中稳定生成图谱边。

```mermaid
flowchart TD
    A[MemoryPage / Scene / Event / Fact] --> B[Story Auto-Link]
    B --> C[Graph Edge Candidates]
    C --> D[校验实体和事件存在]
    D --> E[GraphProjection]
```

它负责：

- 把规范链接转成图谱边；
- 把 frontmatter 字段转成 typed edge；
- 把 Scene 中的实体出场转成 appears_in；
- 把 Event 的参与者、地点、物品转成事件边；
- 把已确认 alias 的解析结果转成稳定实体连接；
- 保持 GraphProjection 可重建。

## 2. Auto-Link 不做什么

Story Auto-Link 不应该：

- 直接从任意原始长文里抽完整知识图谱；
- 自由创造实体；
- 自由创造关系类型；
- 把低置信 alias 强行合并；
- 把模型推测变成 canon；
- 覆盖 SourceSpan 证据链。

## 3. Auto-Link 的输入来源

| 来源 | 例子 | 生成边 |
|---|---|---|
| MemoryPage wikilink | `[[characters/mira-vale]]` | related_to / mentions |
| frontmatter participants | `participants: [Mira, Orrin]` | character present_at event |
| Event location | `location: Harbor Nine` | event occurred_at location |
| Object state | `current_owner: Kestrel` | character owns object |
| Scene mentions | character mention in scene | character appears_in scene |
| AliasRegistry | `Starling -> Mira Vale` | mention resolves_to entity |
| CharacterKnowledge | `knows: secret-x` | character knows fact/event |
| Plotline link | event belongs_to plotline | event related_to plotline |

## 4. 规范链接格式

系统生成的 MemoryPage 可以使用稳定 slug：

```md
[[characters/mira-vale|Mira Vale]]
[[locations/harbor-nine|Harbor Nine]]
[[objects/lantern-map|Lantern Map]]
[[events/lantern-map-stolen|Lantern Map stolen]]
[[plotlines/lantern-map-thread|Lantern Map Thread]]
```

这些链接不是要求作者在正文中手写，而是用于系统生成或作者可编辑的记忆页。

```mermaid
flowchart LR
    A[原始正文] --> B[Mention / Event / Fact]
    B --> C[MemoryPage]
    C --> D[规范 wikilink / frontmatter]
    D --> E[Story Auto-Link]
    E --> F[GraphProjection]
```

## 5. 实体类型白名单

Auto-Link 只识别当前 Story Schema Pack 允许的类型。

Base Story Schema 默认包括：

```text
characters
locations
factions
objects
events
scenes
chapters
plotlines
lore
sources
```

Genre Pack 可以扩展：

```text
sects
artifacts
realms
clues
suspects
ships
planets
technologies
```

## 6. 关系类型白名单

Auto-Link 只生成 schema 中允许的关系。

| 关系 | 来源 | 是否确定性 |
|---|---|---:|
| appears_in | Mention 出现在 Scene | 是 |
| present_at | Event participants | 是 |
| occurred_at | Event location | 是 |
| involves_object | Event objects | 是 |
| owns | Object current_owner | 是，但需状态有效期 |
| member_of | 明确组织归属 | 通常是 |
| knows | CharacterKnowledge | 是，但需证据 |
| reveals | Event / Scene 揭示事实 | 可由事件派生 |
| foreshadows | 标记为伏笔 | 通常需模型或作者判断 |
| contradicts | 冲突检测结果 | 需策略判断 |
| related_to | 弱关联 | 是，但权重低 |

## 7. frontmatter 到边的映射

MemoryPage 和 EventPage 的 frontmatter 可以直接生成边。

```yaml
---
type: event
title: Lantern Map stolen
participants:
  - characters/mira-vale
  - characters/kestrel
location: locations/harbor-nine
objects:
  - objects/lantern-map
plotlines:
  - plotlines/lantern-map-thread
---
```

生成：

```text
characters/mira-vale --present_at--> events/lantern-map-stolen
characters/kestrel --present_at--> events/lantern-map-stolen
events/lantern-map-stolen --occurred_at--> locations/harbor-nine
events/lantern-map-stolen --involves_object--> objects/lantern-map
events/lantern-map-stolen --related_to--> plotlines/lantern-map-thread
```

## 8. Scene membership 到边

只要一个 Mention 解析到实体，并且属于某个 Scene，就可以确定生成 appears_in。

```mermaid
flowchart TD
    A[Mention: Mira] --> B[resolved_to: characters/mira]
    A --> C[scene: ch003-sc002]
    B --> D[appears_in edge]
    C --> D
```

这条边不需要模型判断。

## 9. Event 到 DerivedFacts

Auto-Link 不是所有事实的来源，但可以把事件结构稳定投影为图谱边。

```mermaid
flowchart TD
    A[CanonicalEvent] --> B[participants]
    A --> C[location]
    A --> D[objects]
    A --> E[consequences]
    B --> F[present_at edges]
    C --> G[occurred_at edge]
    D --> H[involves_object edge]
    E --> I[Derived Fact edges]
```

## 10. 高风险边不自动生效

| 边类型 | 风险 | 默认处理 |
|---|---|---|
| alias merge | 可能合并错角色 | 高置信才自动生效 |
| owns | 唯一物品归属冲突 | 检查有效期 |
| knows | 影响 POV 与秘密 | 必须有 evidence |
| family_of | 关系重大 | 需要高置信或作者确认 |
| death | 重大状态 | 需要明确证据 |
| contradicts | 需要解释 | 生成 ReviewItem |

## 11. GraphProjection 可重建

Story Auto-Link 的输出不是源数据，而是投影。

```mermaid
flowchart TD
    A[SourceSpan] --> E[GraphProjection]
    B[Mention] --> E
    C[AliasRegistry] --> E
    D[Event / Fact / MemoryPage] --> E
    E --> F[可删除后重建]
```

如果用户修正 alias、拆分事件、废弃事实，GraphProjection 应该重新生成，而不是手工修补边。

## 12. 避免原始正文污染图谱

原始正文中可能出现类似路径或误导性文本，不应直接被 Auto-Link 当成图边来源。

安全规则：

| 来源 | 是否可直接建图 |
|---|---:|
| Raw Source 原文 | 否，必须经过 Mention / Event / Fact |
| Processed Markdown View | 只用于结构和证据，不直接信任 wikilink |
| MemoryPage | 是，受 schema 校验 |
| Event frontmatter | 是，受 schema 校验 |
| 用户手动 MemoryPage 编辑 | 是，但需要保留变更来源 |
| 低置信模型输出 | 否，只能 proposed |

## 13. 结论

Story Auto-Link 的核心是：

```text
不是从原文自由抽图，而是从已结构化记忆对象中确定性投影故事图谱。
```

这能让小说记忆系统获得稳定、可回放、可调试的图谱，同时保留 SourceSpan 证据和用户校正权。
