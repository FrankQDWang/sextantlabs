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

唯一约束：

```text
unique(source_id, raw_hash)
```

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

字段：`id`, `chapter_id`, `scene_index`, `location_entity_id`, `pov_character_id`, `pov_mode`, `story_time`, `emotional_tone`, `scene_summary`, `scene_function`, `start_offset`, `end_offset`。

唯一约束：

```text
unique(chapter_id, scene_index)
```

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

字段：`id`, `project_id`, `alias_text`, `entity_id`, `alias_type`, `status`, `scope`, `evidence_span_ids jsonb`, `confidence`, `created_at`。

约束：

```text
status in ('auto_accepted', 'proposed', 'rejected', 'user_confirmed', 'user_corrected')
```

### `story_canonical_entities`

字段：`id`, `project_id`, `entity_type`, `display_name`, `canonical_status`, `cast_tier`, `first_seen_scene_id`, `description`, `created_at`, `updated_at`。

`cast_tier` 只适用于 character，不能替代 `canonical_status`。

### `story_event_candidates`

字段：`id`, `project_id`, `scene_id`, `event_type`, `summary`, `participants jsonb`, `objects jsonb`, `location_entity_id`, `state_change jsonb`, `evidence_span_ids jsonb`, `confidence`, `aggregation_status`, `created_at`。

### `story_canonical_events`

字段：`id`, `project_id`, `event_type`, `title`, `event_status`, `primary_scene_id`, `event_candidate_ids jsonb`, `participants jsonb`, `objects jsonb`, `location_entity_id`, `story_time`, `summary`, `consequence_summary`, `evidence_span_ids jsonb`, `created_at`, `updated_at`。

### `story_fact_assertions`

字段：`id`, `project_id`, `subject_ref jsonb`, `predicate`, `object_ref jsonb`, `fact_status`, `valid_from_scene_id`, `valid_until_scene_id`, `evidence_span_ids jsonb`, `confidence`, `source_scope`, `created_at`, `updated_at`。

禁止把 `fact_status='canon'` 作为普通 repository update。必须通过 Canon Promotion use case 写入。

## Memory 与 Review 表

### `memory_evidence_log_entries`

字段：`id`, `project_id`, `log_type`, `target_ref jsonb`, `fact_id`, `event_id`, `source_span_ids jsonb`, `log_status`, `created_at`。

EvidenceLogEntry 允许先写入，Canon Promotion 后写入。

### `memory_character_knowledge`

字段：`id`, `project_id`, `character_id`, `knows_ref jsonb`, `learned_in_scene_id`, `evidence_span_id`, `certainty`, `hidden_from jsonb`, `status`, `created_at`。

### `memory_pages`

字段：`id`, `project_id`, `page_type`, `target_ref jsonb`, `title`, `current_canon jsonb`, `appearance_log jsonb`, `event_log jsonb`, `relationships jsonb`, `open_threads jsonb`, `contradictions jsonb`, `source_refs jsonb`, `canon_status`, `memory_depth`, `updated_at`。

`current_canon` 是综合 read/write object，但不能成为底层事实的唯一来源。所有条目必须能回到 `source_refs`、`fact_id` 或 `event_id`。

### `review_items`

字段：`id`, `project_id`, `review_type`, `severity`, `status`, `summary`, `affected_refs jsonb`, `new_evidence jsonb`, `existing_evidence jsonb`, `suggested_actions jsonb`, `default_action`, `resolution`, `resolved_by`, `resolved_at`, `side_effects jsonb`, `created_at`, `updated_at`。

`review_type` 必须使用 `goals/18-conflict-policy.md` 白名单。

## Agent 与 Storytelling 表

### `agent_action_requests`

字段：`id`, `project_id`, `source_id`, `source_version_id`, `scene_id`, `chapter_id`, `pov_character_id`, `actor_intent`, `trigger`, `action_type`, `target jsonb`, `constraints jsonb`, `expected_output`, `status`, `created_by`, `created_at`。

### `agent_draft_candidates`

字段：`id`, `project_id`, `action_request_id`, `mode`, `candidate_text_ref`, `context_pack_id`, `selected_beat_id`, `target_source_id`, `target_version_id`, `target_scene_id`, `affected_range jsonb`, `base_hash`, `memory_refs jsonb`, `evidence_refs jsonb`, `status`, `author_action`, `accepted_text_ref`, `override_reason`, `created_at`, `updated_at`。

Canonical status values are defined in [04-domain-state-machines.md](04-domain-state-machines.md).

### `agent_review_findings`

字段：`id`, `project_id`, `draft_candidate_id`, `risk_level`, `risk_type`, `summary`, `affected_text_ref`, `memory_refs jsonb`, `storytelling_refs jsonb`, `suggested_revision`, `can_offer_to_author`, `maps_to_review_type_if_accepted`, `draft_local_only`, `created_at`。

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

## Skill、Job、Audit 表

### `skill_runs`

字段：`id`, `project_id`, `skill_name`, `skill_version`, `input_schema_version`, `output_schema_version`, `prompt_version`, `input_hash`, `structured_output jsonb`, `validation_result`, `raw_output_ref`, `status`, `latency_ms`, `cost_cents`, `created_at`。

### `job_records`

字段：`id`, `project_id`, `job_type`, `status`, `idempotency_key`, `payload jsonb`, `attempt_count`, `run_after`, `locked_by`, `locked_at`, `last_error`, `created_at`, `updated_at`。

Unique:

```text
unique(project_id, job_type, idempotency_key)
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
