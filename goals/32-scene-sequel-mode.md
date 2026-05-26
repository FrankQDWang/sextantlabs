# 32. Scene / Sequel Mode

> 本文档定义 Sextant 写作 Agent 如何在逐页推进中判断当前段落是行动场景、反应场景，还是混合段落。这里不讨论实现方式，只讨论叙事模式和写作控制。

## 1. 为什么需要 Scene / Sequel Mode

如果 Agent 不区分段落模式，就容易把动作、解释、内心、设定、回忆混在一起，导致：

- 动作段落被内心说明拖慢；
- 反应段落没有 dilemma 和 decision；
- 角色想法很多，但故事没有推进；
- prose 没有 turn；
- 一段文字只是信息说明，不是故事。

Scene / Sequel Mode 的目标是让 Agent 明确：

```text
当前这段文字到底是在推进冲突，还是在消化后果。
```

## 2. SceneSequelMode 对象

`SceneSequelMode` 是 Storytelling Control Layer 的独立控制产物。它不生成文本，也不直接写 Memory；它会被 `ProseRenderingContract` 消费。

| 字段 | 说明 |
|---|---|
| mode_id | SceneSequelMode ID |
| passage_mode | scene / sequel / mixed |
| mode_rationale | 为什么当前段落应采用该模式 |
| current_pressure | 当前场景压力或上一事件后果 |
| scene_goal | Scene Mode 下角色想达成什么，可为空 |
| opposition | Scene Mode 下阻力来自哪里，可为空 |
| tactic | Scene Mode 下角色采用什么策略，可为空 |
| escalation | Scene Mode 下冲突如何升级，可为空 |
| setback_or_turn | Scene Mode 下目标受阻、代价或小转折，可为空 |
| reaction | Sequel Mode 下角色对后果的反应，可为空 |
| dilemma | Sequel Mode 下角色面对什么困境，可为空 |
| evaluation | Sequel Mode 下各选择代价，可为空 |
| decision | Sequel Mode 下角色做出的决定，可为空 |
| new_goal | Sequel Mode 后产生的下一步目标，可为空 |
| required_turn | 本段必须发生的变化、转折、决定或 hook |
| inner_state_budget | 直接内心说明预算 |
| ending_shape | setback / decision / hook / transition / image |
| agent_review_findings | 可能产生的 AgentReviewFinding 列表 |

## 3. 三种模式

| 模式 | 结构 | 适合用途 |
|---|---|---|
| scene | goal -> conflict -> setback / turn | 行动、对抗、试探、推进剧情 |
| sequel | reaction -> dilemma -> decision | 消化后果、整理情绪、形成下一步目标 |
| mixed | 小动作 + 小反应 + 小决定 | 逐页推进中的过渡段 |

## 4. Scene Mode

Scene Mode 是行动型段落。它要求角色带着目标进入阻力。

```mermaid
flowchart LR
    A[Goal] --> B[Opposition]
    B --> C[Conflict]
    C --> D[Setback / Turn]
```

### Scene Mode 字段

| 字段 | 说明 |
|---|---|
| scene_goal | POV 或驱动角色当前想达成什么 |
| opposition | 阻力来自谁、什么环境、什么信息限制 |
| tactic | 角色采取什么策略 |
| escalation | 冲突如何升级 |
| turn | 本段发生什么小转折 |
| setback | 目标是否受阻，或者得到代价 |

### Scene Mode 对内心戏的限制

| 内容 | 处理 |
|---|---|
| 直接内心说明 | 很少，只允许短句 |
| 情绪 | 通过动作、台词、节奏表现 |
| 非 POV 角色心理 | 不直接写 |
| 设定解释 | 除非影响当前冲突，否则压缩或移除 |

## 5. Sequel Mode

Sequel Mode 是反应型段落。它不只是“想一想”，而是从事件后果中产生下一步决定。

```mermaid
flowchart LR
    A[Reaction] --> B[Dilemma]
    B --> C[Decision]
```

### Sequel Mode 字段

| 字段 | 说明 |
|---|---|
| reaction | 角色对刚发生事件的情绪和身体反应 |
| dilemma | 角色面临什么选择或困境 |
| evaluation | 每个选择的代价 |
| decision | 角色决定下一步做什么 |
| new_goal | 决定带来的下一场景目标 |

### Sequel Mode 对内心戏的允许

Sequel Mode 可以容纳更多内心，但必须服务 dilemma -> decision。

| 好的反应段 | 坏的反应段 |
|---|---|
| 内心推动选择 | 内心反复解释同一情绪 |
| 情绪导致行动 | 情绪只是被描述 |
| 最后形成决定 | 最后仍停在感受 |
| 产生下一步目标 | 没有故事推进 |

## 6. Mixed Mode

逐页推进中，很多段落不是纯 scene 或纯 sequel。Mixed Mode 用于小步过渡。

```text
小行动
  ↓
短反应
  ↓
小选择
  ↓
进入下一步
```

Mixed Mode 适合：

- 场景内部过渡；
- 对话中的短暂停顿；
- 角色意识到某个小问题；
- 从动作转入下一轮行动；
- 一页末尾的微 hook。

## 7. Mode 决策

```mermaid
flowchart TD
    A[当前写作请求] --> B{是否已有明确外部目标?}
    B -->|是| C[Scene Mode]
    B -->|否| D{是否刚发生重要后果?}
    D -->|是| E[Sequel Mode]
    D -->|否| F[Mixed Mode]
    C --> G[SceneSequelMode]
    E --> G
    F --> G
    G --> H[ProseRenderingContract]
```

| 判断问题 | 倾向 Scene | 倾向 Sequel | 倾向 Mixed |
|---|---|---|---|
| 角色是否正在试图达成具体目标 | 是 | 否 | 可能 |
| 是否有明确阻力 | 是 | 否 | 轻微 |
| 是否刚经历后果 | 可能 | 是 | 可能 |
| 当前重点是否是选择 | 可能 | 是 | 是，小选择 |
| 是否需要快速进入下一动作 | 是 | 否 | 是 |

## 8. 与 Character Agency 的关系

Character Agency Pass 给出角色动机；SceneSequelMode 决定这些动机如何进入段落。

| Agency 信息 | Scene Mode 用法 | Sequel Mode 用法 |
|---|---|---|
| immediate_want | 作为 scene_goal | 作为 new_goal 候选 |
| fear | 通过行动回避表现 | 作为 reaction / dilemma |
| moral_boundary | 制造 conflict | 制造 dilemma |
| secret | 通过隐瞒和潜台词表现 | 作为选择代价 |
| relationship_stance | 影响策略 | 影响评估和决定 |

## 9. 与 DramaticBehaviorPlan 的关系

SceneSequelMode 与 DramaticBehaviorPlan 是并行控制产物，由 ProseRenderingContract 汇总。

```mermaid
flowchart LR
    A[Character Agency Pass] --> B[SceneSequelMode]
    A --> C[DramaticBehaviorPlan]
    B --> D[ProseRenderingContract]
    C --> D
```

SceneSequelMode 决定段落结构；DramaticBehaviorPlan 决定内心状态如何呈现。

## 10. 输出给 ProseRenderingContract

SceneSequelMode 会输出：

| 字段 | 说明 |
|---|---|
| passage_mode | scene / sequel / mixed |
| required_goal | 本段必须服务的目标 |
| required_opposition | 本段必须出现的阻力 |
| required_turn | 本段必须有的小转折、决定或 hook |
| inner_state_budget | 直接内心说明预算 |
| ending_shape | setback / decision / hook / transition / image |

## 11. AgentReviewFinding

如果 DraftCandidate 没有满足当前 mode，可产生草稿层风险。所有 risk_type 以 [26-agent-review-policy.md](26-agent-review-policy.md) 第 4 节为唯一 source-of-truth。

| risk_type | 说明 |
|---|---|
| scene_mode_risk | action scene 缺少 goal / opposition / turn |
| sequel_mode_risk | reaction scene 缺少 dilemma / decision |
| mode_mixing_risk | 动作和内心说明混乱，节奏不清 |
| no_turn_risk | 段落没有任何变化或推进 |

这些风险默认是 draft-local，不是正式 Memory ReviewItem。

## 12. 结论

SceneSequelMode 的作用是让逐页写作有段落级结构。

```text
Scene 负责推进冲突。
Sequel 负责消化后果并形成决定。
Mixed 负责小步过渡。
```

它防止 Agent 把角色内心和设定说明堆成流水账。
