# Target Documentation Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct Sextant's target documentation so future work stops treating local prose cue/regex inference as a valid semantic architecture and instead targets a real thin-harness plus rich-skills system.

**Architecture:** This is a documentation-only cleanup. It updates target and status documents to distinguish current useful infrastructure from missing Story Skill architecture, removes misleading guidance about word-list prose semantics, and records the next execution phase as code/test cleanup without performing that cleanup here.

**Tech Stack:** Markdown, `rg`, `git diff --check`, repository-local documentation under `GOAL.md`, `AGENT_GOAL.md`, `goals/`, `implementation/`, `PLAN.md`, `README.md`, and `docs/`.

---

## Scope Guard

This plan modifies target documentation only. Do not edit production code, generated API artifacts, frontend files, backend tests, migrations, prompts, or eval datasets while executing this plan.

Allowed paths:

- `GOAL.md`
- `AGENT_GOAL.md`
- `PLAN.md`
- `README.md`
- `goals/13-skills-and-resolver.md`
- `implementation/00-overview.md`
- `implementation/01-source-of-truth-map.md`
- `implementation/02-module-boundaries.md`
- `implementation/06-story-skills-and-llm-harness.md`
- `implementation/10-worker-and-jobs.md`
- `implementation/13-acceptance-matrix.md`
- `docs/progress-log.md`
- `docs/known-gaps.md`
- `docs/implementation-decisions.md`

Disallowed paths for this plan:

- `backend/`
- `web/`
- `prompts/`
- `evals/`
- `scripts/`
- `.github/`
- `pyproject.toml`
- `uv.lock`
- generated artifacts

The follow-on code/test cleanup is a separate execution phase after this documentation correction is reviewed.

## Source Design

Use this spec as the controlling design input:

- `docs/superpowers/specs/2026-06-29-source-pipeline-cleanup-design.md`

Key requirements from the spec:

- Do not replace invalid word lists with another natural-language cue taxonomy.
- Do not describe prompt registry as Skill Registry.
- State that thin-harness plus rich-skills creative semantic architecture is not complete.
- Preserve useful infrastructure truth: provider ports/adapters, prompt files, prompt hash locking, `SkillRun`, replay diff, worker handlers.
- State missing work: `SkillRegistry`, `run_skill(...)`, resolver, skill document registry, rich-skill semantic layer, Codex subagent judge eval rubric (not production authority), real-corpus chapter/slice evals, RRF fusion, sliding-window organization, hosted/deployed acceptance.
- Keep this plan documentation-only.

## File Responsibility Map

- `GOAL.md`: top-level memory-system target and non-goals. It should state that deterministic logic owns schema/state/evidence, not creative prose semantics.
- `AGENT_GOAL.md`: top-level agent target. It should state that Storytelling Control and Next Page Agent require rich-skill/provider judgment plus deterministic gates, not local cue tables.
- `goals/13-skills-and-resolver.md`: product/domain contract for Story Skills and Resolver. It should define the real thin harness/rich skills split.
- `implementation/06-story-skills-and-llm-harness.md`: engineering contract for `SkillRegistry`, runtime, provider boundary, and evaluation.
- `implementation/00-overview.md`, `implementation/01-source-of-truth-map.md`, `implementation/02-module-boundaries.md`: architecture overview and boundaries. They should align with the corrected skill architecture.
- `PLAN.md`: execution ordering. It should place target-doc cleanup before code/test cleanup and skill-architecture implementation.
- `implementation/13-acceptance-matrix.md`: acceptance gates. It should require doc-cleaned state, no local prose semantic writer, real skill registry, real eval strategy, and no hosted-completion claims from local runs.
- `README.md`: operator-facing current-state summary. It should distinguish current useful infrastructure from missing architecture.
- `docs/progress-log.md`, `docs/known-gaps.md`, `docs/implementation-decisions.md`: status documents. They should stop presenting local prose cue work as completed semantic coverage.

## Task 1: Preflight Documentation Inventory

**Files:**
- Read: `docs/superpowers/specs/2026-06-29-source-pipeline-cleanup-design.md`
- Read: target docs listed in Scope Guard
- Modify: none

- [ ] **Step 1: Confirm the working tree before edits**

Run:

```bash
git status --short --branch
```

Expected: branch status prints successfully. Do not revert unrelated dirty files.

- [ ] **Step 2: Capture current misleading-language hits**

Run:

```bash
rg -n "cue taxonomy|word-list|word list|claim family|prompt registry|SkillRegistry|run_skill|thin harness|rich skills|source-pipeline|source_pipeline|RRF|sliding-window|Fanren|凡人|Codex subagent" GOAL.md AGENT_GOAL.md PLAN.md README.md goals implementation docs
```

Expected: command prints hits that guide the edits. Save no output file; use the output only to choose precise document edits.

- [ ] **Step 3: Verify this plan remains docs-only**

Run:

```bash
git diff --name-only -- backend web prompts evals scripts .github pyproject.toml uv.lock
```

Expected: no new output from this plan's execution.

## Task 2: Correct Top-Level Goal Boundaries

**Files:**
- Modify: `GOAL.md`
- Modify: `AGENT_GOAL.md`

- [ ] **Step 1: Update the deterministic principle in `GOAL.md`**

In `GOAL.md`, replace the existing `Deterministic when possible` table row with this row:

```markdown
| Deterministic for structure and gates | 规则优先处理 schema、枚举、证据链、别名约束、状态转移和 review/canon gate；创作语义理解不能沉进本地词表或 prose regex | [00-design-principles.md](goals/00-design-principles.md)、[13-skills-and-resolver.md](goals/13-skills-and-resolver.md) |
```

- [ ] **Step 2: Insert a hard boundary section in `GOAL.md` after the core principles table**

Insert this section immediately after the core principles table:

```markdown
### 2.1 创作语义边界

Sextant 的确定性层负责稳定系统结构：SourceSpan、EvidenceLogEntry、Story Schema Pack、FactAssertion 状态、ReviewItem gate、CanonPromotion gate、MemoryPage rewrite policy 和 GraphProjection rebuild。

确定性层不负责用自然语言词表理解小说正文。尤其不能把“通报、汇报、声明、报告、说法、消息、话”或英文 communication cue 扩展成一套本地 prose semantic parser。遇到需要判断叙事语义、角色认知、事件归并、POV 含义、戏剧化表达的地方，应由 Story Skill / provider 提出结构化候选，再由确定性 validator 检查 schema、证据边界、source ancestry、review policy 和 canon policy。

Prompt registry 不是 Skill Registry。Prompt 文件、provider adapter、SkillRun audit 是有价值的基础设施，但不等于已经完成 thin harness + rich skills 架构。
```

- [ ] **Step 3: Add a current-state correction in `GOAL.md` before section 8**

Insert this section immediately before `## 8. 当前方案的收敛判断`:

```markdown
## 8. 当前实现状态纠偏

当前代码库已有一部分有意义基础设施：provider ports/adapters、prompt files、prompt hash locking、SkillRun persistence、replay-diff eval、worker handlers、SourceDelta/SourceSpan/EvidenceLogEntry/ReviewItem/MemoryPage/GraphProjection 的生产骨架。

这些不等于 Story Skill 架构完成。当前仍缺少 first-class SkillRegistry、`run_skill(skill_name, skill_version, input_object, runtime_context)` runtime、Resolver、可执行 skill document registry、Codex subagent judge eval rubric (not production authority)、真实语料 chapter/slice eval、RRF keyword+embedding 融合和 gbrain-style sliding-window 自动整理。

已写入 source pipeline 的本地 prose cue/regex 语义推断不是目标能力，应在后续代码/测试清理阶段删除，而不是继续扩展。
```

Renumber the following heading from `## 8. 当前方案的收敛判断` to `## 9. 当前方案的收敛判断`.

- [ ] **Step 4: Update `AGENT_GOAL.md` with the same architecture boundary**

Insert this section immediately after the principles table in `AGENT_GOAL.md`:

```markdown
### 2.1 Agent 语义边界

Storytelling Control、Character Agency Pass、Next Page Agent 和 Agent Review 都属于创作语义工作。它们可以使用 provider / rich skill 提出结构化候选或草稿，但不能把本地词表、regex、固定中文/英文句式当成创作语义架构。

Agent 产物必须保持候选身份：BeatCandidate、DraftCandidate、AgentReviewFinding。正式 SourceDelta、ReviewItem、FactAssertion、CanonPromotion 和 MemoryPage 更新仍由作者接受、证据链、review policy 和 memory gate 决定。
```

- [ ] **Step 5: Verify top-level docs**

Run:

```bash
rg -n "Prompt registry 不是 Skill Registry|创作语义边界|Agent 语义边界|本地 prose cue" GOAL.md AGENT_GOAL.md
```

Expected: all inserted sections are found.

## Task 3: Rewrite Story Skills Target Contract

**Files:**
- Modify: `goals/13-skills-and-resolver.md`

- [ ] **Step 1: Replace the opening note**

Replace the first blockquote under the title with:

```markdown
> 本文档定义 Sextant 记忆系统中的 **thin harness + rich story skills** 目标架构。Harness 只负责装载输入、选择 skill、保存输出、维护证据链和状态转移；创作语义判断沉淀在可审计的 Story Skill 协议和 provider 候选中，并由确定性 validator 裁决是否进入 review/writeback/canon gate。
```

- [ ] **Step 2: Add a non-negotiable boundary after section 2**

Insert this section after the `## 2. 核心分工` table:

```markdown
## 2.1 不可混淆的边界

| 对象 | 是什么 | 不是什么 |
|---|---|---|
| SkillRegistry | 可执行 skill metadata、版本、输入/输出 schema、review/writeback policy、eval contract 的注册表 | prompt 文件目录 |
| Prompt Registry | provider prompt 的加载、metadata 校验和 hash lock | Story Skill 注册机制 |
| Provider Adapter | 调用模型并返回结构化候选 | 生产事实、memory、canon 或 graph 写入者 |
| Deterministic Validator | 检查 schema、SourceSpan、source ancestry、review policy、canon policy | prose 语义解释器 |
| Codex Subagent Judge | eval 阶段的语义复核者 | 生产系统裁决者 |

Story Skill 可以使用 LLM/provider 处理自然语言和创作判断，但最终落库只接受结构化候选通过确定性 gate。不得把中文或英文 cue 词表扩展成“小说语义理解层”。
```

- [ ] **Step 3: Replace the recommended skills table**

Replace the `## 4. 推荐 Story Skills` table with this table:

```markdown
## 4. 初始 Story Skill 目标集合

| Skill | 输入 | 主要输出 | 模型判断 | 是否阻塞主流程 |
|---|---|---|---|---:|
| source-normalization | RawSource / SourceVersion | ProcessedMarkdownView、offset map、cleaning profile | 否 | 是 |
| split-structure | ProcessedMarkdownView | Chapter、Scene、SourceSpan | 可辅助，但结构边界必须可验证 | 是 |
| detect-pov | Scene、mentions、candidate entities | ScenePOV 候选、uncertainty reason | 是 | 否 |
| extract-mentions | SourceSpan、schema pack | Mention | 可辅助 | 否 |
| resolve-alias | Mention、AliasRecord、CanonicalEntity | AliasRecord 候选、ReviewItem 候选 | 可辅助 | 否 |
| extract-events | Scene、mentions、schema pack | EventCandidate | 是 | 否 |
| aggregate-events | EventCandidate、CanonicalEvent | aggregation decision | 是 | 否 |
| derive-facts | CanonicalEvent、accepted evidence | FactAssertion 候选 | 可辅助，但 predicate/type 必须受 schema 约束 | 否 |
| check-continuity | 新候选、canon、POV、timeline | AgentReviewFinding 或 ReviewItem 候选 | 是 | 否 |
| rewrite-current-canon | accepted facts、old MemoryPage | MemoryPage rewrite proposal | 是 | 否 |
| build-writing-context-pack | current position、memory、graph、review | WritingContextPack | 否，排序可使用检索信号 | 不适用 |
| answer-with-evidence | author question、context pack | Evidence-backed answer | 是 | 不适用 |
| character-agency-pass | current pressure、POV、memory | CharacterAgencyState | 是 | 不适用 |
| storytelling-control | agency state、scene mode、author intent | RoleSlot、SceneSequelMode、ProseRenderingContract | 是 | 不适用 |
| next-page-agent | context pack、control objects | BeatCandidate、DraftCandidate | 是 | 不适用 |
| agent-review | draft candidate、contract、risk context | AgentReviewFinding | 是 | 不适用 |
```

- [ ] **Step 4: Extend section 7 with executable metadata**

After the existing section 7 table, add:

````markdown
每个 Story Skill 的文档必须能被实现为 registry metadata。最小字段为：

```text
name
version
trigger
input_schema
output_schema
deterministic_validator
model_judgment_allowed
provider_prompt_ref
review_policy
writeback_policy
eval_cases
negative_cases
judge_rubric
```

`provider_prompt_ref` 可以为空；`deterministic_validator`、`review_policy`、`writeback_policy` 和 `negative_cases` 不可为空。
````

- [ ] **Step 5: Verify no old `fat story skills` wording remains in this file**

Run:

```bash
rg -n "fat story skills|build-next-page-context|cue 词表|词表扩展" goals/13-skills-and-resolver.md
```

Expected: no `fat story skills`; no guidance to expand cue word lists. `build-next-page-context` should be absent or explicitly mapped to `build-writing-context-pack`.

## Task 4: Correct Engineering Skill Harness Contract

**Files:**
- Modify: `implementation/06-story-skills-and-llm-harness.md`

- [ ] **Step 1: Add current-state correction after the title paragraph**

After the first paragraph, insert:

```markdown
## Current Implementation Status

As of 2026-06-29, Sextant has useful provider and audit pieces but not a completed Story Skill architecture.

Implemented pieces:

- provider ports and adapters for StoryDraft, POV Detection, Memory Extraction, Event Aggregation, and Embedding;
- prompt files under `prompts/skills/...`;
- prompt metadata/hash locking through `prompt_registry.py`;
- `SkillRun` persistence and replay-diff evaluation;
- worker job handlers for source, memory, review, context, graph, and agent work.

Missing pieces:

- first-class `SkillRegistry`;
- implemented `run_skill(skill_name, skill_version, input_object, runtime_context) -> SkillRunResult`;
- Resolver from input type/author intent/source type/project policy to Story Skill;
- executable skill document registry;
- rich-skill semantic layer outside `source_pipeline.py`;
- Codex subagent judge eval rubric (not production authority);
- real-corpus chapter/slice skill eval;
- RRF keyword+embedding fusion;
- sliding-window automatic source/context organization.

Prompt registry is not Skill Registry. Provider adapters are not production authority.
```

- [ ] **Step 2: Rename the `Skill Registry` heading**

Change:

```markdown
## Skill Registry
```

to:

```markdown
## Target Skill Registry
```

- [ ] **Step 3: Replace the first production set with the corrected target list**

Replace the existing code block under `First production set:` with:

```text
source-normalization
split-structure
detect-pov
extract-mentions
resolve-alias
extract-events
aggregate-events
derive-facts
check-continuity
rewrite-current-canon
build-writing-context-pack
answer-with-evidence
character-agency-pass
storytelling-control
next-page-agent
agent-review
```

Keep the `build-next-page-context` legacy mapping only if it explicitly says it is not a new skill name.

- [ ] **Step 4: Insert the no-cue-parser rule in `Structured Output`**

After the structured-output pipeline code block, insert:

```markdown
The structured output boundary must not be implemented as a local prose cue parser. Natural-language cues may appear in provider prompts or eval examples, but production validators may only check structured schema, enum membership, SourceSpan ancestry, evidence boundaries, review policy, and writeback/canon policy.
```

- [ ] **Step 5: Replace the live provider test paragraph**

Replace:

```markdown
Live provider tests are optional and never required for PR quick gate.
```

with:

```markdown
Quick-gate replay tests use stored structured outputs. Production readiness still requires real provider E2E validation against fixed source slices, deterministic schema/evidence checks, and Codex subagent judge review with a structured eval rubric; the judge is not production authority. Provider output variability is acceptable only when the invariant checks and eval rubric reject unsupported claims, source-boundary drift, over-inference, missing evidence, and direct memory/canon writes.
```

- [ ] **Step 6: Verify engineering contract wording**

Run:

```bash
rg -n "Current Implementation Status|Prompt registry is not Skill Registry|local prose cue parser|Codex subagent judge eval|not production authority" implementation/06-story-skills-and-llm-harness.md
```

Expected: all corrected clauses are present.

## Task 5: Align Architecture Overview and Module Boundaries

**Files:**
- Modify: `implementation/00-overview.md`
- Modify: `implementation/01-source-of-truth-map.md`
- Modify: `implementation/02-module-boundaries.md`

- [ ] **Step 1: Add architecture correction to `implementation/00-overview.md`**

Insert this section before `## 7. Story Skill 工程协议`:

```markdown
## 6.1 Story Skill 状态纠偏

当前代码库不应被描述为已经完成 thin harness + rich skills。已存在的 provider adapters、prompt registry、SkillRun audit 和 worker handlers 是基础设施，不是完整 SkillRegistry/Resolver。

后续实现顺序必须是：

1. 先清理目标文档中对 local prose cue/regex 语义推断的正向描述；
2. 再删除对应生产代码和测试；
3. 然后实现 first-class SkillRegistry、Resolver、`run_skill(...)` runtime 和 eval rubric；
4. 最后把创作语义候选迁入 rich skills/provider 输出，并由 deterministic validator 裁决。
```

- [ ] **Step 2: Update `implementation/01-source-of-truth-map.md` for goals/13 mapping**

Find the row mapping `goals/13-skills-and-resolver.md`. Replace the whole row with:

```markdown
| `goals/13-skills-and-resolver.md` | `06-story-skills-and-llm-harness.md`, `10-worker-and-jobs.md` | thin harness + rich skills；SkillRegistry/Resolver 是目标能力；prompt registry/provider adapters/SkillRun replay 只是基础设施；skill 不能直接 commit DB 或写 canon |
```

- [ ] **Step 3: Update `implementation/02-module-boundaries.md` skills row**

Find the row for `skills`. Replace the whole row with:

```markdown
| `skills` | Story Skill 协议、skill metadata、deterministic validator、model judgment boundary、review/writeback policy hook、eval rubric | commit DB、直接改 MemoryPage.current_canon、绕过 policy、把 prompt registry 当 SkillRegistry、用 prose cue regex 做创作语义判断 |
```

- [ ] **Step 4: Verify architecture docs**

Run:

```bash
rg -n "Story Skill 状态纠偏|prompt registry/provider adapters/SkillRun replay|把 prompt registry 当 SkillRegistry|prose cue regex" implementation/00-overview.md implementation/01-source-of-truth-map.md implementation/02-module-boundaries.md
```

Expected: each file has its correction.

## Task 6: Update Plan and Acceptance Target

**Files:**
- Modify: `PLAN.md`
- Modify: `implementation/13-acceptance-matrix.md`
- Modify: `README.md`

- [ ] **Step 1: Insert a new first checkpoint in `PLAN.md`**

Insert this section before the first implementation phase/checkpoint in `PLAN.md`:

```markdown
### 0.0 Target Documentation Correction Gate

Before any further code cleanup or feature implementation, update the target documentation to remove the invalid local prose cue/regex semantic direction.

This gate is docs-only. It must:

- state that prompt registry is not Skill Registry;
- state that current thin-harness + rich-skills architecture is incomplete;
- state that local prose cue/regex inference must be deleted, not expanded;
- preserve useful infrastructure as meaningful work;
- list missing work: SkillRegistry, `run_skill(...)`, Resolver, skill document registry, Codex subagent judge eval rubric (not production authority), real-corpus chapter/slice eval, RRF fusion, sliding-window organization, hosted proof, deployed smoke, and clean-context UI acceptance.
```

- [ ] **Step 2: Add code cleanup as a separate next checkpoint in `PLAN.md`**

Immediately after the new `0.0` section, add:

```markdown
### 0.1 Source Pipeline Semantic Cleanup Gate

After target docs are corrected and reviewed, execute a separate code/test cleanup pass.

That pass must remove local prose cue/regex inference paths that create or propose character knowledge, facts, events, relations, review items, memory writeback, canon promotion, graph facts, or POV/scene semantic conclusions. It must also delete or rewrite tests that prove those local prose rules through invented examples.

This gate is intentionally separate from 0.0 so the documentation target is corrected before code edits start.
```

- [ ] **Step 3: Add acceptance rows to `implementation/13-acceptance-matrix.md`**

Add these rows to the relevant Story Skills / provider harness / acceptance table:

```markdown
| target documentation correction | GOAL/AGENT_GOAL/goals/implementation/PLAN/README docs explicitly reject local prose cue/regex semantic inference and distinguish prompt registry from SkillRegistry | `rg` verification plus doc diff review |
| real SkillRegistry target | target docs require first-class SkillRegistry, Resolver, `run_skill(...)`, executable skill document registry, deterministic validators, and rich-skill/provider candidate generation | doc review against `goals/13` and `implementation/06` |
| skill semantic eval target | target docs require fixed source slices, real provider candidate generation, deterministic invariants, and Codex subagent judge eval rubric (not production authority) instead of exact-output LLM assertions | doc review plus future eval harness plan |
```

- [ ] **Step 4: Add current-state correction to `README.md`**

Insert this section near the current status / implementation status area:

```markdown
## Current Architecture Correction

The repository currently contains useful provider/prompt/audit infrastructure, but it has not completed the thin-harness + rich-skills creative semantic architecture.

Implemented infrastructure includes provider ports/adapters, prompt files, prompt hash locking, `SkillRun` persistence, replay-diff evaluation, worker handlers, and the broader source/evidence/review/memory/graph skeleton.

Missing architecture includes first-class `SkillRegistry`, `run_skill(...)`, Resolver, executable skill document registry, rich-skill semantic ownership outside source pipeline, Codex subagent judge eval rubric (not production authority), real-corpus chapter/slice eval, RRF keyword+embedding fusion, sliding-window automatic organization, hosted proof, deployed smoke, and deployed clean-context UI acceptance.

Local prose cue/regex inference in the source pipeline is not a valid completion path and must be removed in a separate cleanup pass.
```

- [ ] **Step 5: Verify plan and README alignment**

Run:

```bash
rg -n "Target Documentation Correction Gate|Source Pipeline Semantic Cleanup Gate|Current Architecture Correction|SkillRegistry|Codex subagent judge eval|not production authority" PLAN.md implementation/13-acceptance-matrix.md README.md
```

Expected: the new gate, acceptance rows, and README correction are present.

## Task 7: Compact Status Documents to Remove Stale Guidance

**Files:**
- Modify: `docs/progress-log.md`
- Modify: `docs/known-gaps.md`
- Modify: `docs/implementation-decisions.md`

- [ ] **Step 1: Replace `docs/progress-log.md` with a compact current record**

Replace the body of `docs/progress-log.md` with this content. Do not move the old body to another repository file; git history is the archive.

```markdown
# Progress Log

## Current Correction - 2026-06-29

The local prose cue/regex semantic extraction direction is superseded and must not guide future implementation. Previous progress entries that described source-pipeline cue families, claim families, communication labels, Chinese/English phrase lists, or invented prose fixtures as semantic coverage are no longer accepted as target progress.

Old detailed progress text remains available in git history only. It must not remain in the working-tree documentation because it pollutes future agent context.

## Meaningful Work to Preserve

- source import/versioning and SourceDelta/SourceSpan/EvidenceLogEntry mechanics;
- persistence, API, worker, review, memory, graph, auth, object-store, observability, and frontend integration skeletons;
- provider ports/adapters, prompt files, prompt hash locks, `SkillRun` persistence, and replay-diff evaluation;
- local and hosted proof runners as infrastructure;
- frontend workbench integration progress when backed by real API/workers.

These items are infrastructure progress only. They do not prove completed creative semantic understanding, hosted readiness, or deployed acceptance.

## Current Required Next Work

1. finish target-documentation correction;
2. remove invalid source-pipeline prose inference code and tests in a separate cleanup pass;
3. implement first-class SkillRegistry, Resolver, `run_skill(...)`, skill document registry, deterministic validators, and rich-skill/provider candidate flow;
4. add real-corpus chapter/slice eval, real provider E2E, Codex subagent judge eval rubric (not production authority), RRF retrieval fusion, sliding-window organization, hosted proof, deployed smoke, and clean-context UI acceptance.

## Verification Status

- Backend, frontend, provider, and browser smoke results recorded before this correction are local evidence only.
- Hosted environment proof, deployed external smoke, and deployed clean-context UI acceptance remain incomplete.
- No production completion claim is valid until source requirements, strict hosted readiness, deployed smoke, and clean-context UI acceptance all pass.
```

- [ ] **Step 2: Replace `docs/known-gaps.md` with corrected active gaps**

Replace the body of `docs/known-gaps.md` with this content. Do not keep the old long completion paragraph in the working tree.

```markdown
# Known Gaps

## Current Gaps Correction - 2026-06-29

The largest current gap is architectural: Sextant has useful provider/prompt/audit infrastructure, but not the completed thin-harness + rich-skills system.

## Active Gaps

- first-class SkillRegistry;
- `run_skill(skill_name, skill_version, input_object, runtime_context) -> SkillRunResult`;
- Resolver;
- executable skill document registry;
- rich-skill creative semantic ownership outside source pipeline;
- Codex subagent judge eval rubric (not production authority);
- real-corpus chapter/slice eval using the ignored local Fanren sample without committing source text;
- RRF keyword+embedding fusion;
- gbrain-style sliding-window automatic organization;
- hosted proof, deployed smoke, and deployed clean-context UI acceptance.

Source-pipeline prose cue/regex inference is not a partial completion of these gaps. It is cleanup debt.

## Useful Existing Infrastructure

- source import/versioning and SourceDelta/SourceSpan/EvidenceLogEntry mechanics;
- persistence, API, worker, review, memory, graph, auth, object-store, observability, and frontend integration skeletons;
- provider ports/adapters, prompt files, prompt hash locks, `SkillRun` persistence, replay-diff evaluation, and provider-boundary guardrails.

## Explicit Non-Completion

- Prompt registry is not SkillRegistry.
- Provider adapters are not Story Skill architecture.
- Local deterministic providers are not semantic quality proof.
- Local green tests are not hosted readiness.
- Browser-only local walkthroughs are not deployed acceptance.
```

- [ ] **Step 3: Replace `docs/implementation-decisions.md` with active decisions**

Replace the body of `docs/implementation-decisions.md` with this content. Do not copy stale cue-parser decisions into an archive file under this repo.

```markdown
# Implementation Decisions

## 2026-06-29 - Supersede Local Prose Cue Semantic Parser Direction

Decision: local prose cue/regex inference must not be treated as Sextant's semantic architecture.

Rationale:

- creative prose semantics should be proposed by rich skills/provider calls, not by source-pipeline word tables;
- deterministic code should validate schema, evidence boundaries, SourceSpan ancestry, review policy, and canon policy;
- prompt registry, provider adapters, and SkillRun replay are useful infrastructure but not SkillRegistry/Resolver;
- self-authored fixture sentences are insufficient to prove semantic generalization.

Consequences:

- target docs must reject local prose cue taxonomy expansion;
- future code cleanup must delete source-pipeline prose inference paths and corresponding tests;
- future skill work must implement SkillRegistry, Resolver, `run_skill(...)`, skill document registry, deterministic validators, real-corpus eval, and Codex subagent judge eval rubric (not production authority).

## 2026-06-29 - Preserve Infrastructure, Not False Completion Claims

Decision: provider ports/adapters, prompt files, prompt hash locking, `SkillRun` persistence, replay-diff evaluation, worker handlers, and source/evidence/review/memory/graph skeletons remain meaningful infrastructure.

Rationale: these pieces are aligned with the production direction when they are not used to claim completed creative semantic understanding.

Consequences:

- keep target docs explicit about what exists;
- keep target docs explicit that SkillRegistry, Resolver, rich-skill semantic layer, real-corpus eval, RRF, sliding-window organization, hosted proof, deployed smoke, and clean-context UI acceptance remain missing;
- do not preserve stale prose-cue progress entries in working-tree docs.

## 2026-06-29 - Documentation Cleanup Before Code Cleanup

Decision: target documentation must be corrected before the next code/test cleanup pass.

Rationale: future Codex goal execution reads repository docs first. Leaving stale target language in place causes agents to keep extending the wrong source-pipeline semantic parser.

Consequences:

- this plan modifies docs only;
- the next execution phase removes invalid production code and tests;
- no production code should be changed during this target-documentation cleanup.
```

- [ ] **Step 4: Verify status docs no longer contain old cue-parser progress blocks**

Run:

```bash
rg -n "claim family|communication label|directed_told_message|passive_claims|source_attributed_acquisition|chinese_cross_scene|通报|汇报|声明|报告|说法|消息" docs/progress-log.md docs/known-gaps.md docs/implementation-decisions.md
```

Expected: no output except lines that explicitly reject or supersede the cue-parser direction. If old positive progress blocks appear, delete them from the working-tree doc.

- [ ] **Step 5: Verify compact status docs begin with current correction**

Run:

```bash
sed -n '1,80p' docs/progress-log.md
sed -n '1,80p' docs/known-gaps.md
sed -n '1,120p' docs/implementation-decisions.md
```

Expected: each file contains only compact current facts and 2026-06-29 decisions, not the old long source-pipeline progress body.

- [ ] **Step 6: Inspect remaining positive guidance hits**

Run:

```bash
rg -n "word-list expansion|cue taxonomy|claim family|communication label|source-pipeline cue|source_pipeline.*semantic|prose cue/regex inference is complete|prompt registry.*SkillRegistry" docs/progress-log.md docs/known-gaps.md docs/implementation-decisions.md
```

Expected: hits either disappear or appear only inside the new superseding correction language that rejects the direction.

## Task 8: Documentation Verification

**Files:**
- Verify: all modified docs

- [ ] **Step 1: Run markdown diff whitespace check**

Run:

```bash
git diff --check -- GOAL.md AGENT_GOAL.md PLAN.md README.md goals implementation docs
```

Expected: no trailing whitespace or whitespace error output.

- [ ] **Step 2: Verify no production paths changed**

Run:

```bash
git diff --name-only -- backend web prompts evals scripts .github pyproject.toml uv.lock
```

Expected: no output.

- [ ] **Step 3: Verify required new target phrases**

Run:

```bash
rg -n "Prompt registry is not Skill Registry|Prompt registry 不是 Skill Registry|first-class SkillRegistry|run_skill\\(skill_name|Codex subagent judge eval|not production authority|real-corpus chapter/slice|RRF keyword\\+embedding|sliding-window" GOAL.md AGENT_GOAL.md PLAN.md README.md goals implementation docs
```

Expected: every required target concept appears in at least one target document, with no phrasing that marks it as complete.

- [ ] **Step 4: Verify rejected direction is not presented as future work**

Run:

```bash
rg -n "expand.*cue|扩展.*词表|词表.*下一步|cue.*next correct|local prose.*valid completion|source-pipeline.*semantic coverage" GOAL.md AGENT_GOAL.md PLAN.md README.md goals implementation docs
```

Expected: no positive guidance to expand local cue/word-list rules. If a hit remains, edit the line so it explicitly rejects or supersedes that direction.

- [ ] **Step 5: Review the final diff by document**

Run:

```bash
git diff --stat -- GOAL.md AGENT_GOAL.md PLAN.md README.md goals implementation docs
git diff -- GOAL.md AGENT_GOAL.md PLAN.md README.md goals/13-skills-and-resolver.md implementation/06-story-skills-and-llm-harness.md implementation/13-acceptance-matrix.md docs/progress-log.md docs/known-gaps.md docs/implementation-decisions.md
```

Expected: changes are documentation-only and aligned with this plan.

## Task 9: Final Handoff

**Files:**
- Read: final diff
- Modify: none unless verification finds a doc issue

- [ ] **Step 1: Summarize what changed**

Prepare a concise handoff with these sections:

```markdown
Changed:
- target docs now reject local prose cue/regex semantic inference;
- target docs distinguish prompt registry/provider adapters/SkillRun replay from real SkillRegistry/Resolver;
- target docs list missing work: SkillRegistry, run_skill runtime, Resolver, skill registry metadata, Codex subagent judge eval review (not production authority), real-corpus eval, RRF fusion, sliding-window organization, hosted/deployed acceptance;
- status docs now supersede old source-pipeline semantic cue progress claims.

Not changed:
- no backend code;
- no frontend code;
- no tests;
- no prompts/evals;
- no generated artifacts.

Verification:
- git diff --check passed for docs;
- backend/web/prompts/evals/scripts/.github paths had no diff from this plan;
- required target phrases were found;
- rejected cue expansion guidance was absent or explicitly superseded.
```

- [ ] **Step 2: Stop before staging or committing**

Do not stage or commit unless the user explicitly asks for that lifecycle step. The final response should say that the plan execution produced docs-only changes and is ready for review.

## Self-Review Checklist

After writing the documentation changes, run this checklist manually:

- [ ] The diff is documentation-only.
- [ ] `prompt registry` is never treated as `SkillRegistry`.
- [ ] Local prose cue/regex inference is never presented as valid future work.
- [ ] The docs preserve useful existing infrastructure without claiming completion.
- [ ] The docs list missing architecture and validation work explicitly.
- [ ] The docs state that code/test cleanup is a separate phase after target-doc correction.
- [ ] The docs mention Codex subagent judge as evaluation support, not production authority.
- [ ] The docs mention real-corpus chapter/slice validation without committing or quoting corpus text.
- [ ] The docs mention RRF fusion and sliding-window organization as missing work.
