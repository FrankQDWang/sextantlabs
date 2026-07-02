# 03. Persistence Schema

本文档定义 Postgres 主库的生产级持久化边界。GraphProjection、ContextPack 和缓存都不是 source of truth；所有事实必须能回到 RawSource、SourceVersion、SourceSpan 或明确用户输入。

## Schema 分组

建议使用单库多 schema 或表名前缀。第一阶段可以使用单 schema + 语义前缀，避免过早引入跨 schema 权限复杂度。

```text
source_*      原始材料、版本、处理视图、证据片段
story_*       章节、场景、提及、别名、实体、事件、事实
memory_*      证据日志、角色认知、记忆页、图谱投影
review_*      ReviewItem 与处理记录
agent_*       ActionRequest、Candidate、AgentReviewFinding、Storytelling Control
skill_*       Skill run、prompt、structured output、golden/eval metadata
job_*         后台 job 和 outbox
audit_*       审计和追踪
```

## Source 与 Evidence 表

### `source_raw_sources`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | uuid | primary key |
| `project_id` | uuid | not null, indexed |
| `source_type` | text | enum check |
| `source_scope` | text | enum check |
| `title` | text | not null |
| `ownership_status` | text | enum check |
| `raw_text_ref` | text | object store ref, not null |
| `created_by` | uuid | nullable for system import |
| `created_at` | timestamptz | not null |

### `source_versions`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | uuid | primary key |
| `source_id` | uuid | fk `source_raw_sources.id`, indexed |
| `version_label` | text | not null |
| `raw_hash` | text | not null |
| `supersedes_version_id` | uuid | nullable self fk |
| `created_at` | timestamptz | not null |

同一 `raw_hash` 可以在同一 source 下出现多次。恢复旧版本必须能创建一个新的
SourceVersion 事件，即使文本内容与历史版本完全相同；版本身份不能被内容哈希去重。

### `source_deltas`

字段：`id`, `project_id`, `source_id`, `previous_version_id`,
`new_version_id`, `accepted_fragment_id`, `delta_kind`, `range_start`,
`range_end`, `base_hash`, `submitted_text_ref`, `submitted_text_search`,
`source_type`, `source_scope`, `provenance jsonb`, `status`, `created_at`。

索引：

```text
(project_id, created_at, id)
(project_id, status, created_at)
gin_trgm(submitted_text_search)
```

`submitted_text_search` 是 SourceDelta 历史检索 read model，不是事实源。
原文仍必须通过 `submitted_text_ref` 从 object store 读取；搜索索引可由
`backend/scripts/reindex_source_delta_search.py` 从 object store 重建。

### `source_processed_views`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | uuid | primary key |
| `version_id` | uuid | fk `source_versions.id`, indexed |
| `cleaning_profile` | text | not null |
| `markdown_ref` | text | object store ref |
| `raw_offset_map_ref` | text | object store ref |
| `view_status` | text | current / stale / rebuilt / deprecated |
| `created_at` | timestamptz | not null |

Partial unique index:

```text
unique(version_id) where view_status = 'current'
```

### `source_spans`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | uuid | primary key |
| `source_id` | uuid | fk |
| `version_id` | uuid | fk |
| `view_id` | uuid | fk |
| `chapter_id` | uuid | nullable fk |
| `scene_id` | uuid | nullable fk |
| `start_offset` | integer | not null, >= 0 |
| `end_offset` | integer | not null, > start_offset |
| `raw_start_offset` | integer | not null |
| `raw_end_offset` | integer | not null |
| `text_preview` | text | bounded length |
| `speaker_entity_id` | uuid | nullable |
| `narration_layer` | text | enum check |

Required check:

```text
end_offset > start_offset
raw_end_offset > raw_start_offset
```

## Story Structure 表

### `story_chapters`

字段：`id`, `view_id`, `chapter_index`, `title`, `start_offset`, `end_offset`, `summary`, `created_at`。

唯一约束：

```text
unique(view_id, chapter_index)
```

### `story_scenes`

字段：`id`, `chapter_id`, `scene_index`, `location_entity_id`, `pov_character_id`, `pov_mode`, `pov_confidence`, `pov_evidence_span_ids jsonb`, `pov_uncertainty_reason`, `story_time`, `emotional_tone`, `scene_summary`, `scene_function`, `start_offset`, `end_offset`。

唯一约束：

```text
unique(chapter_id, scene_index)
```

## Story Schema Pack 表

### `story_schema_packs`

字段：`id`, `project_id nullable`, `pack_type`, `pack_name`, `version`,
`status`, `entity_types jsonb`, `event_types jsonb`, `relations jsonb`,
`extraction_hints jsonb`, `risk_rules jsonb`, `created_at`, `updated_at`。

约束：

```text
pack_type in ('base', 'genre', 'project_override')
status in ('active', 'deprecated')
project_id is null for base/genre packs
project_id is not null for project_override packs
unique(pack_type, pack_name, version) where project_id is null
unique(project_id, pack_type, pack_name, version) where project_id is not null
```

`entity_types` entries must carry a `name`. Genre or project override entity
types that declare `subtype_of` inherit relation behavior from their base type.
Extension entity types without `subtype_of` are allowed only for weak
`related_to` graph participation until a later schema decision assigns a base
subtype. Worker fact derivation must reject stronger relation attempts for
those weak entity types before FactAssertion or GraphProjection side effects.

`risk_rules.disabled_event_types` can remove event types from the effective
project schema. SourceSpan event extraction must skip those event candidates and
audit the schema decision instead of writing EventCandidate, CanonicalEvent, or
event-derived FactAssertion rows.

`risk_rules.disabled_relations` can remove relation predicates from the
effective project schema. SourceSpan fact derivation must audit
`schema_relation_not_allowed` and skip the write before any FactAssertion,
CharacterKnowledge, MemoryPage, EvidenceLogEntry, or GraphProjection side
effect.

`relations` may be plain names or structured definitions. Structured Genre
Pack and Project Override relations use:

```json
{
  "name": "guards",
  "subject_types": ["character", "faction"],
  "object_types": ["location", "object"]
}
```

The effective schema compiler must preserve these subject/object role contracts
and remove them when `risk_rules.disabled_relations` disables the relation.
Fact validation must reject custom relation role mismatches with
`schema_relation_role_not_allowed` before evidence, memory, review, or graph
side effects.

`extraction_hints.relation_patterns` may declare deterministic SourceSpan
templates for custom relations:

```json
{
  "relation": "master_of",
  "template": "{subject} is {object}'s master",
  "subject_type": "character",
  "object_type": "character"
}
```

The worker may derive the relation only when both placeholders resolve to
same-SourceSpan mentions whose entity types match the effective schema and the
rendered template text appears in the source span. The derived fact still goes
through the normal SourceSpan evidence, FactAssertion, conflict policy,
MemoryPage, and GraphProjection path.

`extraction_hints.mention_patterns` may declare deterministic SourceSpan
templates for project-specific entity mentions:

```json
{
  "entity_type": "artifact",
  "template": "Relic: {mention}",
  "confidence": 0.84
}
```

`entity_type` must be present in the effective schema and `template` must
contain `{mention}`. The mention keeps the custom schema type, so downstream
FactAssertion refs may use `artifact`; the linked CanonicalEntity row still
stores the nearest allowed base subtype such as `object` to preserve the
database CanonicalEntity type constraint.

`extraction_hints.event_patterns` may declare deterministic SourceSpan
templates for project-specific event candidates:

```json
{
  "event_type": "ritual",
  "template": "{subject} sealed the rite at {location}",
  "subject_type": "character",
  "location_type": "location",
  "confidence": 0.84
}
```

`event_type` must be present in the effective schema, `template` must contain
`{subject}`, and each placeholder type must be present in the effective schema.
The worker may create a StoryEventCandidate only when the rendered template
appears in the SourceSpan after same-SourceSpan mentions have resolved. The
event still goes through CanonicalEvent aggregation and normal
SourceSpan-backed fact derivation.

GraphProjection is a derived read model over FactAssertions and confirmed
CanonicalEvent structures, not a fact source. FactAssertions with statuses
`canon`, `proposed`, `inferred`, `disputed`, `contradicted`, or `outdated` may
project as graph edges with the matching `edge_status`; `user_note` facts remain
outside graph projection. Its edge `relation` must preserve predicates that are
allowed by the project's effective Story Schema, including custom Genre Pack or
Project Override relations such as `master_of`. Unknown or out-of-schema legacy
fact predicates may be projected as `related_to`, but they must not create new
FactAssertion rows. The `memory_graph_projection_edges.relation` column
therefore cannot use a static Base relation check constraint.

GraphProjection direct CanonicalEvent auto-link may project confirmed event
participants, locations, and objects as `present_at`, `occurred_at`, and
`involves_object` edges only after the same effective schema/ref/role validation
passes. The edge identity is `(project_id, source_ref, subject_ref, relation,
target_ref)` so one CanonicalEvent can project multiple participant edges to the
same event without conflict.

### `project_story_schema_bindings`

字段：`id`, `project_id`, `base_schema_pack_id`, `genre_schema_pack_id nullable`,
`project_override_pack_id nullable`, `status`, `created_by`, `created_at`,
`updated_at`。

约束：

```text
status in ('active', 'superseded')
unique(project_id) where status = 'active'
```

When no active binding exists, application code reads the immutable Base Story
Schema. Active bindings merge Base + optional Genre Pack + optional Project
Override into the final project schema used by extraction and validation paths.
Genre Pack selection writes create a new active binding and supersede the
previous binding while preserving the current Project Override pack ref. Genre
Pack rows are global active `story_schema_packs` with `pack_type='genre'` and
`project_id is null`; selecting a deprecated, project-scoped, missing, or
non-genre pack is rejected before binding changes.
System-admin Genre Pack provisioning creates global active `genre` rows through
idempotent API writes after effective-schema validation. Deprecation changes
only the pack status to `deprecated`, requires system-admin authorization, and
is rejected while any active ProjectStorySchemaBinding still references the
pack, so an existing project's effective schema is not silently changed.
Project Override edits are written by versioning a new project-scoped
`story_schema_packs` row and creating a new active
`project_story_schema_bindings` row while superseding the previous binding.
That write changes only schema configuration and audit/idempotency records; it
does not create SourceDelta, evidence, memory, review, canon, or
GraphProjection side effects.

## Entity、Event、Fact 表

### `story_mentions`

字段：`id`, `span_id`, `raw_text`, `mention_type`, `local_context`, `resolved_entity_id`, `resolution_status`, `confidence`, `created_at`。

索引：

```text
(span_id)
(resolved_entity_id)
gin_trgm(raw_text)
```

### `story_alias_records`

字段：`id`, `project_id`, `alias_text`, `entity_id`, `alias_type`, `status`, `scope`, `valid_from_scene_id`, `valid_until_scene_id`, `evidence_span_ids jsonb`, `confidence`, `created_at`。

约束：

```text
status in ('auto_accepted', 'proposed', 'low_confidence', 'rejected', 'user_confirmed', 'user_corrected')
```

### `story_canonical_entities`

字段：`id`, `project_id`, `entity_type`, `display_name`, `canonical_status`, `cast_tier`, `first_seen_scene_id`, `description`, `created_at`, `updated_at`。

`cast_tier` 只适用于 character，不能替代 `canonical_status`。

约束：

```text
entity_type in Base Story Schema entity types plus other
canonical_status in ('canon', 'draft', 'provisional', 'discarded', 'contradicted')
cast_tier is null or cast_tier in ('local_extra', 'minor_supporting', 'recurring', 'major', 'unknown')
cast_tier is null unless entity_type = 'character'
```

### `story_event_candidates`

字段：`id`, `project_id`, `scene_id`, `event_type`, `summary`, `participants jsonb`, `objects jsonb`, `location_entity_id`, `state_change jsonb`, `evidence_span_ids jsonb`, `confidence`, `aggregation_status`, `created_at`。

约束：

```text
aggregation_status in ('new', 'merged', 'related', 'conflict_version', 'rejected')
```

### `story_canonical_events`

字段：`id`, `project_id`, `event_type`, `title`, `event_status`, `primary_scene_id`, `event_candidate_ids jsonb`, `participants jsonb`, `objects jsonb`, `location_entity_id`, `story_time`, `summary`, `cause_summary`, `consequence_summary`, `evidence_span_ids jsonb`, `created_at`, `updated_at`。

约束：

```text
event_status in ('proposed', 'canon', 'disputed', 'deprecated', 'external_canon', 'author_note')
```

### `story_fact_assertions`

字段：`id`, `project_id`, `subject_ref jsonb`, `predicate`, `object_ref jsonb`, `fact_status`, `valid_from_scene_id`, `valid_until_scene_id`, `evidence_span_ids jsonb`, `confidence`, `source_scope`, `created_at`, `updated_at`。

`predicate` must use the effective Story Schema relation whitelist. Character
knowledge certainty such as `suspected`, `false_belief`, and `misunderstands`
must not create ad hoc predicates; use `knows` / `does_not_know` plus
`memory_character_knowledge.certainty` and knowledge-claim metadata. Worker
fact derivation validates the effective relation whitelist before fact dedup,
evidence merge, insert, or downstream canon/review side effects. Base Story
Schema relations also validate documented subject/object roles before write;
for example, `present_at` requires a character/faction subject and event
object, while `owns` requires a character/faction subject and object target.
Genre Pack and Project Override structured relation definitions use the same
effective-schema role gate for custom relation predicates.
Knowledge relations allow documented secret targets, so `knows` /
`does_not_know` may point to `secret` refs as well as events,
knowledge-claims, and lore. Grouped memory writeback provider facts use the
same effective-schema predicate/ref/role gate before normalized views, spans,
evidence, facts, review items, memory pages, or graph edges are written.
Refs whose `type` is neither an effective schema entity type nor an explicitly
allowed non-entity fact ref type are rejected before FactAssertion side effects.
Refs must also carry a stable `id` unless they are literal values with `value`;
malformed refs are audited and skipped before evidence or graph writes.

禁止把 `fact_status='canon'` 作为普通 repository update。必须通过 Canon Promotion use case 写入。

## Memory 与 Review 表

### `memory_evidence_log_entries`

字段：`id`, `project_id`, `log_type`, `target_ref jsonb`, `fact_id`, `event_id`, `source_span_ids jsonb`, `log_status`, `created_at`。

EvidenceLogEntry 允许先写入，Canon Promotion 后写入。

### `memory_character_knowledge`

字段：`id`, `project_id`, `character_id`, `knows_ref jsonb`, `learned_in_scene_id`, `evidence_span_id`, `certainty`, `hidden_from jsonb`, `status`, `created_at`。

约束：

```text
certainty in ('known', 'suspected', 'false_belief', 'misunderstands', 'does_not_know')
status in ('active', 'superseded')
```

### `memory_pages`

字段：`id`, `project_id`, `page_type`, `target_ref jsonb`, `title`, `current_canon jsonb`, `appearance_log jsonb`, `event_log jsonb`, `relationships jsonb`, `open_threads jsonb`, `contradictions jsonb`, `source_refs jsonb`, `canon_status`, `memory_depth`, `updated_at`。

`current_canon` 是综合 read/write object，但不能成为底层事实的唯一来源。所有条目必须能回到 `source_refs`、`fact_id` 或 `event_id`。

### `semantic_embeddings`

字段：`id`, `project_id`, `target_type`, `target_id`, `target_ref jsonb`,
`text_hash`, `provider`, `model_name`, `dimensions`, `vector jsonb`,
`embedding_vector vector`（PostgreSQL + pgvector 可用时）, `evidence_refs jsonb`,
`updated_at`。

约束：

```text
target_type in ('memory_page', 'source_span', 'style_sample')
dimensions > 0
unique(project_id, target_type, target_id, provider, model_name)
```

当前实现使用真实 DB 持久化 MemoryPage、SourceSpan、style_sample
embedding 索引，并由 `refresh_semantic_index` worker job 刷新。JSONB/JSON
`vector` 是可移植持久化副本；PostgreSQL + pgvector 环境通过
`embedding_vector` 存储 pgvector 值，并由部署/烟测路径按当前
`dimensions` 创建 HNSW cosine expression index
`ix_semantic_embeddings_embedding_vector_hnsw`。运行时只有在 extension、
vector 列和该索引都存在时才使用 pgvector `<=>` ranking，否则回退到
有界应用侧 cosine ranking。该索引不能写 FactAssertion、MemoryPage、Canon
或 GraphProjection，只能作为 ContextPack/MemoryAnswer relevance 召回线索。

### `review_items`

字段：`id`, `project_id`, `review_type`, `severity`, `status`, `summary`, `affected_refs jsonb`, `new_evidence jsonb`, `existing_evidence jsonb`, `suggested_actions jsonb`, `default_action`, `resolution`, `resolved_by`, `resolved_at`, `side_effects jsonb`, `created_at`, `updated_at`。

`review_type` 必须使用 `goals/18-conflict-policy.md` 白名单。

## Agent 与 Storytelling 表

### `agent_action_requests`

字段：`id`, `project_id`, `source_id`, `source_version_id`, `scene_id`, `chapter_id`, `pov_character_id`, `actor_intent`, `trigger`, `action_type`, `target jsonb`, `constraints jsonb`, `expected_output`, `status`, `created_by`, `created_at`。

### `agent_draft_candidates`

字段：`id`, `project_id`, `action_request_id`, `mode`, `candidate_text_ref`, `context_pack_id`, `selected_beat_id`, `target_source_id`, `target_version_id`, `target_scene_id`, `affected_range jsonb`, `base_hash`, `memory_refs jsonb`, `evidence_refs jsonb`, `status`, `author_action`, `accepted_text_ref`, `override_reason`, `created_at`, `updated_at`。

Canonical status values are defined in [04-domain-state-machines.md](04-domain-state-machines.md).

### `agent_beat_candidates`

字段：`id`, `project_id`, `action_request_id`, `context_pack_id`, `target_source_id`, `target_version_id`, `target_scene_id`, `affected_range jsonb`, `base_hash`, `summary`, `driver_character`, `agency_rationale`, `storytelling_rationale`, `cast_decision jsonb`, `tension`, `memory_refs jsonb`, `evidence_refs jsonb`, `status`, `selected_at`, `created_at`。

BeatCandidate 是候选方向，不是正文。它可以被后续 DraftCandidate 通过
`selected_beat_id` 引用，但不能直接成为 SourceDelta、MemoryPage、Canon 或
ReviewItem。

### `agent_review_findings`

字段：`id`, `project_id`, `action_request_id`, `draft_candidate_id nullable`, `risk_level`, `risk_type`, `summary`, `affected_text_ref`, `memory_refs jsonb`, `storytelling_refs jsonb`, `suggested_revision`, `can_offer_to_author`, `maps_to_review_type_if_accepted`, `draft_local_only`, `created_at`。

`action_request_id` is required for every AgentReviewFinding. `draft_candidate_id`
is nullable because explicit `check_risk` actions can return draft-local risk
findings without creating a DraftCandidate.

### `agent_storytelling_controls`

一张表保存 schema-versioned control payload，或拆成多张表。第一阶段建议统一表：

字段：`id`, `project_id`, `action_request_id`, `draft_candidate_id`, `control_type`, `schema_version`, `payload jsonb`, `created_at`。

`control_type` 白名单：

```text
role_slot
character_casting_decision
new_character_seed
scene_sequel_mode
dramatic_behavior_plan
prose_rendering_contract
```

### `context_pack_readiness`

字段：`id`, `project_id`, `source_span_id`, `source_delta_id nullable`, `status`, `reason`, `affected_refs jsonb`, `evidence_refs jsonb`, `created_at`, `updated_at`。

ContextPackReadiness 只记录 Memory / Review / Graph 依赖已经变更，等待作者请求续写或问答时按需生成 ContextPack。它不是完整 ContextPack，也不能反写 Memory、Canon 或 GraphProjection。作者请求生成的 WritingContextPack 只会把该 ContextPack `evidence_refs` 覆盖到的 SourceSpan readiness 标为 `consumed`。

Unique:

```text
unique(project_id, source_span_id, reason)
```

约束：

```text
status in ('pending', 'stale', 'consumed')
reason in ('memory_dependency_changed', 'review_dependency_changed')
```

## Skill、Job、Audit 表

### `skill_runs`

字段：`id`, `project_id`, `skill_name`, `skill_version`, `input_schema_version`, `output_schema_version`, `prompt_version`, `input_hash`, `structured_output jsonb`, `validation_result`, `raw_output_ref`, `status`, `latency_ms`, `cost_cents`, `created_at`。

### `job_records`

字段：`id`, `project_id`, `job_type`, `status`, `idempotency_key`, `payload jsonb`, `attempt_count`, `run_after`, `locked_by`, `locked_at`, `last_error`, `created_at`, `updated_at`。

`payload` must include `step` equal to `job_type` and a non-empty
`pipeline_version`; the DB worker validates this before handler execution.

Unique:

```text
unique(project_id, job_type, idempotency_key)
```

约束：

```text
job_type in (
  'normalize_source',
  'split_structure',
  'run_memory_writeback',
  'extract_mentions',
  'resolve_aliases',
  'extract_events',
  'aggregate_events',
  'derive_facts',
  'run_conflict_policy',
  'rewrite_memory_page',
  'rebuild_graph_projection',
  'build_context_pack',
  'run_agent_candidate',
  'run_agent_review',
  'run_skill_replay_eval'
)
status in ('queued', 'running', 'succeeded', 'failed_retryable', 'failed_terminal', 'cancelled')
```

### `audit_events`

字段：`id`, `project_id`, `request_id`, `actor_id`, `event_type`, `subject_ref jsonb`, `decision jsonb`, `created_at`。

不得把完整手稿明文写入 audit event。

## Transaction 边界

| Use case | 同一事务内必须完成 | 禁止同事务执行 |
|---|---|---|
| `SubmitActionRequest` | request 持久化、幂等记录 | LLM 调用 |
| `AcceptCandidate` | candidate 状态变更、AcceptedFragment、SourceDelta | Memory extraction 全管线 |
| `CreateSourceDelta` | SourceVersion、ProcessedMarkdownView job、audit | Canon promotion |
| `RunMemoryWriteback` | SourceSpan、Mention、EventCandidate、EvidenceLogEntry、ReviewItem candidate | 外部长 LLM 调用可拆 job |
| `PromoteCanon` | Fact status、MemoryPage rewrite、GraphProjection stale mark、audit | 原始材料删除 |
| `ResolveReviewItem` | review status、side effects、projection stale mark | 新模型判断 |

## Migration 规则

1. 所有 schema 变更必须走 Alembic。
2. 影响 source-of-truth 的 migration 必须在 PR body 标记。
3. 删除列必须两阶段：deprecate -> code no longer reads -> delete。
4. enum 扩展必须同步 `goals/` 或 `implementation/` 白名单。
5. migration upgrade 必须在 CI 运行。
6. production migration 之前必须有 backup/rollback note。

## 验收

Persistence PR 通过条件：

1. Alembic upgrade 在空库通过。
2. SourceSpan range check、current ProcessedMarkdownView partial unique index 存在。
3. `model_suggestion` 不能自动升格为 canon 的测试存在。
4. ReviewItem 类型白名单和 AgentReviewFinding 类型白名单被测试覆盖。
5. GraphProjection 可删除重建的 integration test 存在。
