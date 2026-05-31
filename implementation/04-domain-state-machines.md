# 04. Domain State Machines

本文档定义生产实现必须保护的状态机。状态机属于 domain 层，API、worker、skill 和前端只能通过 use case 触发状态迁移。

## DraftCandidate

Canonical 状态来自 `goals/24-draft-candidate-lifecycle.md`。

```text
generated
  -> reviewed
  -> offered_to_author
  -> accepted
  -> converted_to_source_delta

generated
  -> reviewed
  -> blocked
  -> revised
  -> reviewed

offered_to_author
  -> revised
  -> reviewed

offered_to_author
  -> rejected
  -> archived

blocked
  -> offered_to_author  (explicit author override only)
```

允许状态：

```text
generated
reviewed
offered_to_author
accepted
revised
rejected
blocked
archived
converted_to_source_delta
```

UI 可以显示 `proposed`、`rerolled`、`partially accepted` 等产品语言，但后端持久状态以本节为准。

## DraftCandidate 迁移规则

| From | To | 触发 | 必须校验 |
|---|---|---|---|
| generated | reviewed | Agent Review 完成 | review result schema valid |
| reviewed | offered_to_author | 可交付作者 | high-risk finding 不阻断或已标明 |
| reviewed | blocked | 严重风险 | 至少一个 high risk AgentReviewFinding |
| blocked | revised | 作者或 Agent 要求修改 | 原 high risk 保留 |
| blocked | offered_to_author | explicit override | `override_reason` not null |
| offered_to_author | accepted | 作者采纳 | accepted text ref exists |
| offered_to_author | revised | 作者要求改 | revision instruction exists |
| offered_to_author | rejected | 作者拒绝 | no SourceDelta |
| accepted | converted_to_source_delta | SourceDelta 创建成功 | target base_hash 校验 |
| rejected | archived | 历史归档 | no downstream memory refs |

禁止：

```text
generated -> accepted
blocked -> accepted
rejected -> accepted
any -> converted_to_source_delta without accepted_text_ref
```

## AcceptedFragment

AcceptedFragment 不是独立长期事实源，它是从 candidate 到 SourceDelta 的 provenance。

状态可以保持轻量：

```text
created
  -> source_delta_created
  -> superseded_by_text_edit
```

规则：

1. AcceptedFragment 表示作者接受具体文本进入目标位置。
2. AcceptedFragment 不代表作者确认所有推断事实成立。
3. partial accept 必须记录接受文本范围和目标 range。

## SourceDelta

状态：

```text
submitted
  -> source_version_created
  -> normalized
  -> span_extracted
  -> memory_writeback_queued
  -> memory_writeback_completed

submitted
  -> rejected_stale_base
```

规则：

1. replace 型 SourceDelta 必须校验 `base_hash` 或 `previous_version_id`。
2. stale base 不允许静默覆盖。
3. SourceDelta 可以失败，但 RawSource / SourceVersion 不应被半写入污染。

## ProcessedMarkdownView

状态：

```text
current
stale
rebuilt
deprecated
```

规则：

1. 同一 SourceVersion 最多一个 current view。
2. 新 cleaning profile 产生 rebuilt view 时，旧 current 先变 stale。
3. SourceSpan 必须引用明确 view_id，不能只引用 source/version。

## AliasRecord

状态：

```text
proposed
  -> auto_accepted
  -> user_confirmed
  -> user_corrected
  -> rejected
```

规则：

1. alias_conflict 阻断强合并，不阻断 ingest。
2. user_corrected 必须生成纠错 audit signal。
3. scene_local alias 不能默认扩大为 global。

## EventCandidate

状态：

```text
new
  -> merged
  -> related
  -> conflict_version
  -> rejected
```

规则：

1. `merged` 必须指向 CanonicalEvent。
2. `conflict_version` 必须生成 ReviewItem 或 disputed relation。
3. `rejected` 不能删除 evidence。

## CanonicalEvent

状态：

```text
proposed
  -> canon
  -> disputed
  -> deprecated
  -> external_canon
  -> author_note
```

规则：

1. `canon` 必须由 policy 或作者明确接受触发。
2. external canon 不能默认覆盖 user draft。
3. deprecated 事件仍保留 evidence 和替代关系。

## FactAssertion

状态：

```text
proposed
  -> inferred
  -> canon
  -> disputed
  -> contradicted
  -> outdated
  -> user_note
```

Canon promotion gate：

```text
FactAssertion(proposed/inferred)
  -> EvidenceLogEntry
  -> ConflictPolicyDecision
  -> canon OR disputed/ReviewItem
```

禁止：

```text
model output -> canon
skill output -> canon
api request -> canon
GraphProjection edge -> FactAssertion
```

## ReviewItem

状态来自 `goals/18-conflict-policy.md`：

```text
open
  -> resolved
  -> dismissed
  -> superseded

dismissed
  -> open

resolved
  -> superseded
```

Resolution 白名单：

```text
accept
reject
split
merge
mark_intentional
supersede
needs_memory_update
fixed_by_text_edit
accepted_as_change
```

规则：

1. ReviewItem 不阻断正文保存。
2. high severity 阻断自动 canon promotion。
3. dismissed 不等于 resolved。
4. superseded 必须记录替代 ReviewItem 或新 evidence。

## AgentReviewFinding

AgentReviewFinding 是草稿层风险，不进入 Memory Review 生命周期。

字段约束：

```text
risk_level in low / medium / high
risk_type in goals/26 whitelist
draft_local_only true for style/storytelling-only risks
maps_to_review_type_if_accepted nullable
```

状态可以由 DraftCandidate 生命周期隐含，不需要单独状态机。

## Storytelling Control Objects

以下对象是草稿层控制产物：

```text
RoleSlot
CharacterCastingDecision
NewCharacterSeed
SceneSequelMode
DramaticBehaviorPlan
ProseRenderingContract
```

规则：

1. 它们不写 Memory。
2. 它们可以引用 Memory 和 risk context。
3. 它们只能通过 DraftCandidate 被作者接受后间接进入 SourceDelta。
4. NewCharacterSeed 接受后由 Memory ingest 决定 Mention、CanonicalEntity、MemoryPage 落点。

## Job

状态：

```text
queued
  -> running
  -> succeeded
  -> failed_retryable
  -> failed_terminal
  -> cancelled
```

规则：

1. retryable job 必须有 idempotency key。
2. worker crash 后 locked job 可被 lease timeout 释放。
3. terminal failure 必须写 audit event。

## 验收

状态机 PR 通过条件：

1. 每个状态迁移有 unit test。
2. 至少测试 5 条禁止迁移。
3. Candidate stale base 不能生成 SourceDelta。
4. AgentReviewFinding 不能创建 ReviewItem 的测试存在。
5. FactAssertion 不能直接从 proposed 写 canon 的测试存在。
