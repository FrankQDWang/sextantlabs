# Progress Log

Current-state note: the 2026-07-02 source coverage refresh near the end of
this file supersedes older 2026-06-29 and early 2026-07-01 `remaining=` text
where later hosted proof checkpoints closed those external evidence items.
Historical checkpoints are retained for auditability and should not be read as
the latest status without the refresh section.

## Goal Intake Coverage Audit - 2026-06-29

Audit basis:

- read `AGENTS.md`, `PLAN.md`, `GOAL.md`, `AGENT_GOAL.md`, every Markdown file under `goals/`, `experience/`, `implementation/`, `docs/`, `README.md`, `web/README.md`, plus goal-start extras `PRODUCT.md` and `prompts/skills/*.md`;
- audited live implementation surface under `backend/src/sextant`, `backend/tests`, `backend/scripts`, `scripts/`, `web/components/workbench`, `web/lib`, `web/tests`, `web/e2e`, and `web/src/generated`;
- preserved the dirty branch in place; no reset, revert, or destructive git command was used.

Status legend:

- `local`: repo contains concrete code/tests for the file's obligations, with current local verification recorded in the 2026-07-01 checkpoints below when applicable.
- `partial`: obligations are only partly realized locally, or the file explicitly requires architecture/proof that the repo still lacks.
- `blocked-external`: the repo has the production path/config gate, but completion still depends on hosted credentials, deployment, or external evidence.
- `status-doc`: the file is itself a status/control document whose truth must be kept aligned with live code and verification.

Evidence bundles used below:

- `B1` core memory/evidence path: `backend/src/sextant/domain/*`, `backend/src/sextant/application/use_cases.py`, `backend/src/sextant/infra/{source_pipeline.py,memory_writeback.py,memory_page_rewrite.py,uow.py,context_readiness.py,graph_projection.py}`; tests `backend/tests/integration/{test_memory_writeback.py,test_application_use_cases.py,test_persistence_schema.py,test_source_pipeline_cleanup.py}` and `backend/tests/unit/test_domain_state_machines.py`.
- `B2` API/contracts/auth: `backend/src/sextant/api/{app.py,schemas.py}`, `backend/src/sextant/contracts/use_cases.py`, `backend/tests/integration/{test_api_contracts.py,test_auth.py,test_runtime_app.py}`, `backend/tests/contract/test_generated_api_artifacts.py`, `web/src/generated/sextant-api.ts`, `web/tests/{sextant-api.test.ts,workbench-api.test.ts}`.
- `B3` workers/ops/security: `backend/src/sextant/infra/{worker.py,worker_handlers.py,worker_health.py,worker_metrics.py,observability.py,provider_secrets.py,object_store.py}`, `backend/scripts/*.py`, `scripts/*.sh`, tests `backend/tests/integration/{test_worker_jobs.py,test_worker_healthcheck.py,test_production_config_gate.py,test_postgres_smoke_gate.py,test_object_store.py,test_provider_secrets.py}`, `backend/tests/security/{test_observability_redaction.py,test_semgrep_rules.py}`.
- `B4` agent/storytelling control: `backend/src/sextant/domain/{agent.py,agent_risk.py,story.py,story_schema.py,prose_contract_review.py}`, `backend/src/sextant/infra/{agent_candidate.py,agent_review.py,story_draft_provider.py,story_draft_openai.py,semantic_search.py,source_delta_search.py}`, tests `backend/tests/integration/{test_action_request_run.py,test_agent_candidate_job.py,test_agent_review_job.py,test_story_draft_provider.py,test_memory_answer_context_pack.py}`, `backend/tests/unit/{test_agent_risk_language.py,test_prose_contract_review.py,test_story_schema.py}`.
- `B5` web workbench integration: `web/components/workbench/*`, `web/lib/{workbench-api.ts,workbench-display.ts,workbench-data.ts}`, `web/tests/*`, `web/e2e/workbench.spec.ts`.
- `B6` provider prompts/evals: `prompts/skills/*.md`, `backend/src/sextant/infra/{openai_compat.py,prompt_registry.py,provider_runtime.py,provider_usage.py,event_aggregation_provider.py,memory_extraction_provider.py,pov_detection_provider.py,story_draft_provider.py,skill_replay_eval.py}`, tests `backend/tests/integration/{test_event_aggregation_provider.py,test_memory_extraction_provider.py,test_pov_detection_provider.py,test_story_draft_provider.py,test_openai_compat_runtime.py}`, `backend/tests/golden/test_provider_golden.py`, `backend/tests/contract/test_prompt_registry.py`.
- `B7` hosted readiness and deployment gates: `docs/deployment-runbook.md`, `backend/scripts/hosted_*`, `scripts/validate-production-config.sh`, `scripts/validate-hosted-readiness.sh`, tests `backend/tests/integration/test_hosted_*.py` and `test_production_config_gate.py`.
- `B8` story-skill runtime and retrieval proof: `backend/src/sextant/{ports/story_skills.py,infra/story_skill_registry.py,infra/real_corpus_skill_eval.py,infra/retrieval_fusion.py,infra/semantic_search.py,infra/source_pipeline.py,infra/memory_writeback.py,infra/uow.py}`, `backend/scripts/real_corpus_memory_boundary_eval.py`, `evals/datasets/real_corpus_memory_boundary/*.json`, tests `backend/tests/integration/{test_story_skill_runtime.py,test_real_corpus_skill_eval.py,test_memory_answer_context_pack.py,test_story_draft_provider.py,test_agent_candidate_job.py,test_memory_writeback.py,test_source_pipeline_cleanup.py}`.

### Entry, Product, and Status Docs

- `AGENTS.md`: `status=blocked-external`; obligations=source-order execution, full source coverage, dirty-tree protection, doc upkeep, and browser/computer-use clean-context acceptance; remaining=intake discipline and local verification are complete, but deployed clean-context UI acceptance still requires external hosted proof; evidence=this section, 2026-07-01 checkpoints below, `docs/implementation-decisions.md`, no destructive git activity in this run.
- `GOAL.md`: `status=local`; obligations=evidence-backed memory system, canon/review gates, retrieval, graph, and author-sovereign writeback path; remaining=local verification passed in the 2026-07-01 checkpoint; hosted/deployed proof remains external; evidence=`B1+B2+B3`.
- `AGENT_GOAL.md`: `status=local`; obligations=writing-context-pack-driven agent loop, draft candidate lifecycle, author acceptance, and review-aware agent behavior; remaining=local verification passed in the 2026-07-01 checkpoint; deployed clean-context UI proof remains external; evidence=`B4+B2+B5`.
- `PLAN.md`: `status=blocked-external`; obligations=force complete source coverage, production implementation, hosted readiness, and final acceptance without scope collapse; remaining=local implementation and verification checkpoints are recorded below, while hosted proof, deployed smoke, and deployed clean-context acceptance remain externally blocked; evidence=this section, `B1+B2+B3+B4+B5+B7+B8`.
- `README.md`: `status=local`; obligations=truthful repo map, runbooks, and verification contract aligned to live code; remaining=local commands and claims were checked in the 2026-07-01 verification checkpoints; hosted proof remains external to README-local completion; evidence=`B2+B3+B5+B7+B8`.
- `PRODUCT.md`: `status=local`; obligations=quiet author-sovereign visual/product direction, no demo-style UI, accessibility expectations; remaining=local frontend verification passed; deployed clean-context UI acceptance proof remains external; evidence=`web/components/workbench/*`, `web/tests/*`, `web/e2e/workbench.spec.ts`.
- `docs/progress-log.md`: `status=status-doc`; obligations=record live checkpoints, source coverage, evidence, and non-completion truth; remaining=update after each verification or implementation checkpoint; evidence=this section plus prior cleanup entry.
- `docs/implementation-decisions.md`: `status=status-doc`; obligations=record scope judgments, conflicts, architecture, dependency, persistence, security, and testing decisions; remaining=append new decisions whenever implementation or verification changes scope truth; evidence=current file plus the intake decisions added in this run.
- `docs/known-gaps.md`: `status=status-doc`; obligations=record only real residual gaps or exact external blockers; remaining=current as of the 2026-07-01 hosted gate recheck; update when proof refs or hosted credentials exist; evidence=current file plus `B7`.
- `docs/goal-readiness-review.md`: `status=status-doc`; obligations=state release/readiness truth without overstating completion; remaining=current as of the 2026-07-01 local verification and hosted blocker recheck; evidence=`B2+B3+B5+B7+B8`.
- `docs/deployment-runbook.md`: `status=blocked-external`; obligations=production deployment, hosted probes, rollout, rollback, and evidence archival; remaining=completion depends on real hosted environment, credentials, deployment version, and proof refs; evidence=`B7`.
- `docs/superpowers/plans/2026-06-29-target-documentation-cleanup.md`: `status=local`; obligations=correct docs away from local prose regex semantics and preserve only truthful infrastructure claims; remaining=the local follow-on architecture work it called out was completed on 2026-07-01; external provider/hosted proof is still separate; evidence=current docs plus `B6+B8`.
- `docs/superpowers/specs/2026-06-29-source-pipeline-cleanup-design.md`: `status=local`; obligations=remove local prose semantic parsing and leave creative semantics to rich skills/provider output; remaining=provider live E2E and hosted/deployed proof remain external to the local repo pass; evidence=`B1+B6+B8`.

### Experience Contracts

- `experience/README.md`: `status=local`; obligations=bind the product flow across writing, candidate, writeback, review, and conversation surfaces; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B1+B2+B4+B5`.
- `experience/00-product-principles.md`: `status=local`; obligations=author sovereignty, evidence traceability, and non-demo behavior; remaining=local non-demo behavior and frontend verification passed; hosted/deployed proof remains external; evidence=`B1+B2+B5`.
- `experience/01-writing-session-loop.md`: `status=local`; obligations=real session loop from source/draft through acceptance and writeback-visible consequences; remaining=local API-mode and e2e verification passed in the 2026-07-01 checkpoint; deployed proof remains external; evidence=`B1+B2+B4+B5`, `web/e2e/workbench.spec.ts`.
- `experience/02-action-request-contract.md`: `status=local`; obligations=typed ActionRequest creation, execution, status, and audit; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/contracts/use_cases.py`, `backend/src/sextant/application/use_cases.py`, `backend/tests/integration/{test_action_request_run.py,test_api_contracts.py}`, `B2`.
- `experience/03-candidate-lifecycle.md`: `status=local`; obligations=draft candidate states, author actions, overrides, and accepted-fragment backwrite; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B4`, `backend/tests/integration/test_api_contracts.py`, `backend/tests/unit/test_domain_state_machines.py`.
- `experience/04-memory-writeback-contract.md`: `status=local`; obligations=preview, review, canon gate, and evidence-backed writeback; remaining=local verification passed in the 2026-07-01 checkpoint; hosted proof remains external; evidence=`B1+B2`, `backend/tests/integration/test_memory_writeback.py`, `web/components/workbench/memory-writeback.tsx`, `web/tests/memory-writeback.test.tsx`.
- `experience/05-review-and-risk-contract.md`: `status=local`; obligations=review types, dispute/risk handling, and non-canon risk surfacing; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B1+B2+B4`, `web/components/workbench/review-badge.tsx`, `web/tests/review-badge.test.tsx`.
- `experience/06-conversational-entry-contract.md`: `status=local`; obligations=memory-answer entry backed by evidence/context rather than ad hoc chat; remaining=local API-mode verification passed in the 2026-07-01 checkpoint; deployed clean-context acceptance proof remains external; evidence=`B1+B2+B4+B5`, `backend/tests/integration/test_memory_answer_context_pack.py`, `web/components/workbench/memory-answer-panel.tsx`, `web/tests/memory-answer-panel.test.tsx`.

### Goals 00-12: Memory Core

- `goals/00-design-principles.md`: `status=local`; obligations=evidence-first architecture, author control, deterministic policy boundaries; remaining=local verification passed in the 2026-07-01 checkpoint; final hosted proof remains external; evidence=`B1+B2+B5`.
- `goals/01-data-flow.md`: `status=local`; obligations=source-to-memory-to-candidate round-trip; remaining=local API, worker, frontend, and e2e verification passed in the 2026-07-01 checkpoint; hosted proof remains external; evidence=`B1+B2+B4+B5`.
- `goals/02-core-data-structures.md`: `status=local`; obligations=domain entities for source, evidence, memory, review, graph, and agent surfaces; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/domain/*`, `backend/src/sextant/infra/db/models.py`, `B1+B4`.
- `goals/03-source-evidence.md`: `status=local`; obligations=`SourceDelta`, `SourceSpan`, `EvidenceLogEntry`, ancestry, and no evidence bypass; remaining=local verification passed in the 2026-07-01 checkpoint; deployed hosted smoke remains external; evidence=`B1`, `backend/tests/integration/{test_persistence_schema.py,test_memory_writeback.py,test_api_contracts.py}`.
- `goals/04-scenes-pov.md`: `status=local`; obligations=scene modeling, POV constraints, and provider-boundary POV adjudication without local prose heuristics; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/infra/{source_pipeline.py,pov_detection_provider.py,pov_detection_openai.py}`, `B6`, `backend/tests/integration/test_pov_detection_provider.py`.
- `goals/05-mentions-aliases.md`: `status=local`; obligations=mention extraction, alias resolution, and ambiguity review rather than silent collapse; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/infra/source_pipeline.py`, `backend/tests/integration/{test_source_pipeline_cleanup.py,test_memory_writeback.py}`, `B1`.
- `goals/06-entities-events-facts.md`: `status=local`; obligations=entity/event/fact modeling and evidence-backed fact derivation with conflict handling; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B1+B6`, `backend/tests/integration/{test_event_aggregation_provider.py,test_memory_writeback.py}`.
- `goals/07-memory-pages.md`: `status=local`; obligations=memory page materialization, rewrite workflow, and canon-vs-proposed separation; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/infra/{memory_writeback.py,memory_page_rewrite.py,uow.py}`, `backend/tests/integration/test_memory_writeback.py`, `web/components/workbench/memory-page-panel.tsx`, `web/tests/memory-page-panel.test.tsx`.
- `goals/08-graph-projection.md`: `status=local`; obligations=rebuildable graph edges that never become fact authority; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/infra/graph_projection.py`, `backend/src/sextant/infra/uow.py`, `backend/tests/integration/test_memory_writeback.py`, `web/tests/memory-page-panel.test.tsx`.
- `goals/09-retrieval-context-pack.md`: `status=local`; obligations=context-pack retrieval, readiness state, and retrieval-backed memory answers; remaining=provider live E2E proof and hosted/deployed proof still sit outside this local pass; evidence=`backend/src/sextant/infra/{semantic_search.py,source_delta_search.py,context_pack_job.py,context_readiness.py,uow.py,retrieval_fusion.py}`, `backend/tests/integration/test_memory_answer_context_pack.py`, `web/components/workbench/scene-card.tsx`, `web/tests/scene-card.test.tsx`, `B8`.
- `goals/10-continuity-check.md`: `status=local`; obligations=continuity answer surface with evidence, caveats, and unknowns; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/infra/uow.py` continuity answer paths, `backend/tests/integration/test_memory_answer_context_pack.py`, `web/components/workbench/memory-answer-panel.tsx`, `web/tests/memory-answer-panel.test.tsx`.
- `goals/11-non-goals.md`: `status=local`; obligations=avoid chat-first authorship takeover, non-evidenced canon writes, and graph-as-truth shortcuts; remaining=deployed final acceptance proof remains external; evidence=`B1+B2+B4+B5`.
- `goals/12-inspirations.md`: `status=local`; obligations=maintain the intended product shape without broad redesign or chat collapse; remaining=deployed clean-context UI acceptance proof remains external; evidence=`PRODUCT.md`, `web/components/workbench/*`, `web/tests/*`.

### Goals 13-19: Skills, Source Normalization, and Writeback Policy

- `goals/13-skills-and-resolver.md`: `status=local`; obligations=first-class Story Skills, `SkillRegistry`, `Resolver`, skill metadata/runtime, and deterministic validator boundary; remaining=provider live E2E proof and hosted/deployed proof still require external evidence; evidence=`B6+B8`, `backend/src/sextant/infra/story_skill_registry.py`, `backend/src/sextant/infra/skill_replay_eval.py`, `backend/tests/integration/test_story_skill_runtime.py`.
- `goals/14-story-schema-packs.md`: `status=local`; obligations=project/story schema pack storage, API, validation, and replayable edits; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/api/app.py`, `backend/src/sextant/contracts/use_cases.py`, `backend/tests/integration/test_api_contracts.py`, `backend/tests/unit/test_story_schema.py`.
- `goals/15-event-aggregation.md`: `status=local`; obligations=provider-boundary event aggregation with deterministic adjudication outcomes; remaining=provider live E2E proof remains external; evidence=`backend/src/sextant/infra/{event_aggregation_provider.py,event_aggregation_openai.py}`, `prompts/skills/openai_event_aggregation/openai-event-aggregation.v1.md`, `backend/tests/integration/test_event_aggregation_provider.py`, `backend/tests/golden/test_provider_golden.py`.
- `goals/16-source-normalization.md`: `status=local`; obligations=normalized source views and source-version handling before downstream derivation; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/infra/source_normalization.py`, `backend/src/sextant/infra/source_structure.py`, `backend/tests/integration/{test_persistence_schema.py,test_api_contracts.py}`, `B1`.
- `goals/17-incremental-memory-writeback.md`: `status=local`; obligations=incremental writeback with preview, idempotency, and review/canon gating; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B1+B2`, `backend/tests/integration/test_memory_writeback.py`.
- `goals/18-conflict-policy.md`: `status=local`; obligations=dispute policy, overrides, and blocked canon promotion flows; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/application/use_cases.py`, `backend/src/sextant/api/app.py`, `backend/tests/integration/test_api_contracts.py`, `backend/tests/integration/test_memory_writeback.py`.
- `goals/19-story-auto-link.md`: `status=local`; obligations=SourceDelta search/indexing and auto-link support across new sources; remaining=hosted reindex proof still external; evidence=`backend/src/sextant/infra/source_delta_search.py`, `backend/scripts/reindex_source_delta_search.py`, `backend/tests/integration/test_source_delta_reindex.py`, `scripts/source-delta-reindex-smoke.sh`, `B7`.

### Goals 20-33: Agent and Storytelling Control

- `goals/20-agent-overview.md`: `status=local`; obligations=agent proposal loop stays downstream of memory/context and upstream of author acceptance; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B4+B5`.
- `goals/21-writing-context-pack.md`: `status=local`; obligations=build/read WritingContextPack with memory, graph, and review-aware context; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B4`, `backend/tests/integration/test_memory_answer_context_pack.py`, `web/components/workbench/scene-card.tsx`.
- `goals/22-character-agency-profile.md`: `status=local`; obligations=character agency/risk signals feed candidate review without direct canon writes; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/domain/agent_risk.py`, `backend/src/sextant/infra/agent_review.py`, `backend/tests/unit/test_agent_risk_language.py`, `backend/tests/integration/test_agent_review_job.py`.
- `goals/23-next-page-agent.md`: `status=local`; obligations=next-page drafting through provider/story-skill boundary into author-reviewable candidates; remaining=provider live E2E proof remains external; evidence=`backend/src/sextant/infra/{agent_candidate.py,story_draft_provider.py,story_draft_openai.py}`, `prompts/skills/openai_story_draft/openai-story-draft.v1.md`, `backend/tests/integration/test_agent_candidate_job.py`, `web/components/workbench/candidate-drawer.tsx`.
- `goals/24-draft-candidate-lifecycle.md`: `status=local`; obligations=candidate states, acceptance/rejection/override, and accepted fragment backwrite; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B4+B2`, `backend/tests/integration/test_api_contracts.py`, `web/tests/candidate-drawer.test.tsx`.
- `goals/25-agent-memory-writeback.md`: `status=local`; obligations=accepted agent output re-enters the same evidence/writeback path as any other source; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B1+B4`, `backend/tests/integration/{test_action_request_run.py,test_memory_writeback.py}`.
- `goals/26-agent-review-policy.md`: `status=local`; obligations=agent review findings stay distinct from `ReviewItem` and route through formal review operations; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/domain/review.py`, `backend/src/sextant/infra/agent_review.py`, `backend/tests/integration/test_agent_review_job.py`, `web/tests/review-badge.test.tsx`.
- `goals/27-storytelling-control-layer.md`: `status=local`; obligations=storytelling control objects constrain generation without becoming memory/canon authority; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B4`, `backend/tests/unit/test_story_schema.py`, `backend/tests/integration/test_api_contracts.py`.
- `goals/28-role-need-and-cast-expansion.md`: `status=local`; obligations=role-need and cast-expansion structures feed candidate generation with policy constraints; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/domain/story_schema.py`, `backend/src/sextant/contracts/use_cases.py`, `backend/tests/integration/test_api_contracts.py`.
- `goals/29-new-character-policy.md`: `status=local`; obligations=new-character seeds and policy gating before durable story adoption; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B4`, `backend/tests/integration/test_agent_candidate_job.py`, `backend/tests/integration/test_api_contracts.py`.
- `goals/30-dramatization-layer.md`: `status=local`; obligations=dramatization controls stay in generation/review space, not canon space; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B4`, `backend/src/sextant/domain/story.py`, `backend/tests/integration/test_agent_candidate_job.py`.
- `goals/31-inner-state-rendering.md`: `status=local`; obligations=inner-state rendering constraints and review-safe prose generation; remaining=provider live E2E proof remains external; evidence=`B4`, `prompts/skills/openai_story_draft/openai-story-draft.v1.md`, `backend/tests/golden/test_provider_golden.py`.
- `goals/32-scene-sequel-mode.md`: `status=local`; obligations=scene/sequel mode constraints flow through story schema and candidate generation; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/domain/story_schema.py`, `backend/tests/unit/test_story_schema.py`, `backend/tests/integration/test_api_contracts.py`.
- `goals/33-prose-rendering-contract.md`: `status=local`; obligations=prose rendering contract shapes provider output and candidate review without direct memory/canon authority; remaining=provider live E2E and deployed clean-context acceptance proof remain external; evidence=`B4+B6`, `web/components/workbench/editor.tsx`, `web/tests/editor.test.tsx`.

### Implementation Specs

- `implementation/README.md`: `status=local`; obligations=map engineering specs to implementation surfaces; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B1+B2+B3+B4+B5`.
- `implementation/00-overview.md`: `status=local`; obligations=overall architecture truth; remaining=must keep distinguishing local architecture completion from still-missing hosted/deployed proof; evidence=`B1+B2+B4+B6+B8`.
- `implementation/01-source-of-truth-map.md`: `status=local`; obligations=map source documents to concrete code areas; remaining=keep aligned with current implementation during verification; evidence=this coverage audit plus `B1+B2+B4+B5`.
- `implementation/02-module-boundaries.md`: `status=local`; obligations=separate domain/application/api/infra/skills boundaries and forbid prompt-registry-as-skill-registry shortcuts; remaining=local `tach` verification passed in the 2026-07-01 checkpoint; evidence=repo module layout under `backend/src/sextant/*`, `B1+B2+B4+B6`.
- `implementation/03-persistence-schema.md`: `status=local`; obligations=relational schema, migrations, constraints, idempotency tables, and lifecycle persistence; remaining=hosted Postgres proof is external; evidence=`backend/src/sextant/infra/db/models.py`, `backend/migrations`, `backend/tests/integration/{test_migrations.py,test_persistence_schema.py}`, `B7`.
- `implementation/04-domain-state-machines.md`: `status=local`; obligations=explicit lifecycle transitions and deterministic invalid-transition failures; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/domain/{agent.py,memory.py,review.py,story.py}`, `backend/tests/unit/test_domain_state_machines.py`.
- `implementation/05-application-use-cases.md`: `status=local`; obligations=typed use cases for source ingest, writeback, review, conversation, and candidate operations; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`backend/src/sextant/application/use_cases.py`, `backend/tests/integration/{test_application_use_cases.py,test_api_contracts.py}`.
- `implementation/06-story-skills-and-llm-harness.md`: `status=local`; obligations=thin harness plus rich skills, `SkillRegistry`, `Resolver`, replay/eval/runtime contracts, and provider boundary; remaining=provider live E2E proof and hosted/deployed proof remain external to the local repo pass; evidence=`B6+B8`, `backend/src/sextant/infra/story_skill_registry.py`, `backend/src/sextant/infra/real_corpus_skill_eval.py`, `backend/src/sextant/infra/skill_replay_eval.py`.
- `implementation/07-agent-and-storytelling-control.md`: `status=local`; obligations=agent/story control structures, candidate policies, and control surfaces; remaining=local verification passed in the 2026-07-01 checkpoint; evidence=`B4+B5`.
- `implementation/08-api-contracts.md`: `status=local`; obligations=typed request/response schemas, idempotent writes, deterministic errors, and generated client sync; remaining=local artifact generation and contract verification passed in the 2026-07-01 checkpoint; evidence=`B2`, `web/src/generated/sextant-api.ts`.
- `implementation/09-frontend-integration.md`: `status=local`; obligations=API-backed workbench behavior without broad redesign; remaining=deployed clean-context UI acceptance proof remains external; evidence=`B5`, `web/lib/workbench-api.ts`, `web/e2e/workbench.spec.ts`.
- `implementation/10-worker-and-jobs.md`: `status=local`; obligations=worker catalog, job handlers, retries, health, and pipeline execution; remaining=hosted worker-capacity proof is external; evidence=`B3`, `backend/tests/integration/{test_worker_jobs.py,test_worker_healthcheck.py}`.
- `implementation/11-ci-cd-and-ai-guardrails.md`: `status=local`; obligations=CI/security/guardrail checks, replay tests, and anti-fake completion controls; remaining=local command verification passed in the 2026-07-01 checkpoint; evidence=`.github/workflows/{ci.yml,security.yml}`, `B3+B6`.
- `implementation/12-observability-security-ops.md`: `status=hosted`; obligations=observability, redaction, hosted secrets/session/object-store/post-deploy ops evidence; remaining=hosted observability, Supabase Vault runtime, session/token, invitation delivery, object-store IAM, backup/restore, smoke, worker, rollback, and reindex proof now have evidence; direct SSH operational access remains a non-readiness ops TODO because deployment used KiwiVM/R2 handoff; evidence=`B3+B7` plus the 2026-07-01 hosted proof checkpoints below.
- `implementation/13-acceptance-matrix.md`: `status=hosted`; obligations=all acceptance rows must pass or be marked exact external blockers with evidence; remaining=hosted-readiness gate returns `hosted-readiness-config-ok`; final completion still requires rerunning the required verification set and clean-context UI acceptance after this last deploy; evidence=`B1+B2+B3+B4+B5+B7+B8` plus the 2026-07-01 hosted proof checkpoints below.
- `implementation/14-implementation-pr-stack.md`: `status=local`; obligations=decompose delivery ordering and dependencies; remaining=useful as sequencing reference, but not itself completion evidence; evidence=current repo surface across `B1-B7`.

### Web and Prompt Surface Docs

- `web/README.md`: `status=local`; obligations=frontend setup, API-mode runtime, test commands, and workbench behavior expectations; remaining=frontend lint/typecheck/build/test/e2e passed in the 2026-07-01 checkpoint; evidence=`B5`, `scripts/dev-workbench.sh`.
- `prompts/skills/openai_event_aggregation/openai-event-aggregation.v1.md`: `status=local`; obligations=structured event-adjudication prompt with no canon authority and evidence requirement; remaining=depends on provider/runtime verification rather than prompt text alone; evidence=`B6`.
- `prompts/skills/openai_memory_extraction/openai-memory-extraction.v1.md`: `status=local`; obligations=structured memory/thread candidate extraction with no direct memory/canon authority; remaining=depends on provider/runtime verification rather than prompt text alone; evidence=`B6`.
- `prompts/skills/openai_pov_detection/openai-pov-detection.v1.md`: `status=local`; obligations=structured POV detection from provided mentions only; remaining=depends on provider/runtime verification rather than prompt text alone; evidence=`B6`.
- `prompts/skills/openai_story_draft/openai-story-draft.v1.md`: `status=local`; obligations=story-draft generation under POV/risk constraints and no canon authority; remaining=depends on provider/runtime verification rather than prompt text alone; evidence=`B4+B6`.

## Current Execution Focus - 2026-06-29

1. verify the repo's actual backend/frontend/worker/security command surface against `README.md` and `implementation/13-acceptance-matrix.md`;
2. determine which open items are real missing implementation versus external hosted blockers;
3. implement remaining local gaps under TDD only after the verification pass identifies exact failures;
4. update this log after every verification or implementation checkpoint.

## Verification Checkpoint - 2026-06-29 - Static and Backend Suite

Passed in the live working tree:

- `uv run --python /opt/homebrew/bin/python3 ruff check backend/src backend/tests backend/migrations backend/scripts`
- `uv run --python /opt/homebrew/bin/python3 ty check backend/src`
- `uv run --python /opt/homebrew/bin/python3 tach check`
- `uv run --python /opt/homebrew/bin/python3 semgrep --config .semgrep/sextant.yml backend/src --error --quiet`
- `uv run --python /opt/homebrew/bin/python3 pytest backend/tests`
- `pnpm --dir web lint`
- `pnpm --dir web typecheck`

Observed results:

- backend static boundaries, type checks, dependency layering, and Semgrep rules all passed without findings;
- backend test suite passed `603` tests in `90.89s` with one external-library deprecation warning from `fastapi.testclient` / `starlette.testclient`;
- the current repo state is not a hollow scaffold: API contracts, persistence, writeback, worker jobs, provider adapters, hosted probe config gates, and security/redaction tests are all green locally;
- the remaining local verification items listed here were completed in the 2026-07-01 full verification checkpoint below; only externally sourced hosted proof remains open.

## Verification Checkpoint - 2026-06-29 - Full Local Runtime and Browser Acceptance

Passed in the live working tree:

- `pnpm --dir web build`
- `pnpm --dir web test`
- `SEXTANT_DATABASE_URL=sqlite+pysqlite:////tmp/sextant-alembic-verify.sqlite uv run --python /opt/homebrew/bin/python3 alembic upgrade head`
- `uv run --python /opt/homebrew/bin/python3 python backend/scripts/generate_api_artifacts.py`
- `uv run --python /opt/homebrew/bin/python3 python backend/scripts/production_smoke.py`
- `pnpm --dir web exec playwright test -g "workbench runs backend-backed candidate and writeback flow"`
- `pnpm --dir web test:e2e`
- `uv run --python /opt/homebrew/bin/python3 pytest backend/tests/integration/test_dev_workbench_script.py -q -p no:tach`

Observed results:

- frontend production build passed; Vitest passed `14` files / `106` tests;
- SQLite-backed Alembic upgrade reached head successfully when using the README-documented local override instead of an unavailable default Postgres instance;
- API artifact generation completed without drift output;
- `production_smoke.py` passed the real local production path: migration, ActionRequest, DraftCandidate, agent risk check, candidate acceptance, worker writeback, MemoryWritebackPreview, and evidence-backed MemoryAnswer;
- full Playwright suite passed `6` scenarios after updating the stale natural-language-to-memory assumption in `web/e2e/workbench.spec.ts` to match the current deterministic local provider boundary;
- `scripts/dev-workbench.sh` is now repeatable on the same state dir: a new regression test proved `--prepare-only` succeeds on consecutive runs.

Clean-context browser acceptance evidence:

- started the real local workbench through `bash scripts/dev-workbench.sh` after the repeatable-seed fix;
- opened the live UI in the in-app browser at `http://127.0.0.1:5800` without reading source or docs during acceptance;
- verified the clean-context opening surface: `Ch.03 西档案室`, `v1`, `POV · 当前 POV`, `2 个待处理`, current scene card, and seeded pressure/open-thread items;
- triggered `问 Sextant -> 续写这一段 给出几条候选`, received a real candidate drawer, selected one sentence, accepted it, and observed the UI advance to `v2` with a completed writeback job and real evidence-backed preview;
- opened the memory panel in the same live session and verified the `Starling` memory page plus graph inspector visible from the running backend.

Remaining non-local completion items after this checkpoint:

- hosted/deployed acceptance still depends on production configuration, deployment URLs, credentials, proof refs, and external smoke/clean-context evidence;
- the 2026-06-29 note that local Story Skill/runtime architecture was still open was superseded by the 2026-07-01 implementation checkpoint below.

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

1. keep local docs and verification evidence aligned with the implemented Story Skill runtime, real-corpus eval, RRF retrieval fusion, and sliding-window context organization;
2. collect the remaining external evidence: real provider E2E, hosted proof, deployed smoke, and deployed clean-context UI acceptance.

## Cleanup Execution - 2026-06-29

- removed local prose cue/regex semantic mention, POV, knowledge-transfer, cross-scene communication, agency-profile, and schema relation/event parsing paths from `backend/src/sextant/infra/source_pipeline.py`;
- removed remaining summary-based transfer ownership/review heuristics and dead cue/taxonomy residue from `backend/src/sextant/infra/source_pipeline.py`; structured ownership now requires explicit candidate roles instead of local prose inference;
- removed local prose ownership inference fallback from `backend/src/sextant/skills/local_memory_extractor.py`; only explicit structured `FACT:` and `THREAD:` directives remain in the local provider;
- replaced the old source-pipeline semantic positive suite with boundary-focused cleanup coverage in `backend/tests/integration/test_source_pipeline_cleanup.py`;
- deleted obsolete semantic suites `backend/tests/integration/test_source_pipeline_jobs.py` and `backend/tests/unit/test_source_pipeline_parsing.py`.

## Preserved After Cleanup

- `split_structure`, `SourceSpan`, evidence ancestry, review, memory, and graph infrastructure;
- explicit scene metadata handling such as `POV:` and `Location:` lines;
- alias resolution, provider-boundary POV adjudication over preseeded mentions, event aggregation, fact conflict policy, and structured memory directive parsing.

## Verification Status

- Backend, frontend, provider, and browser smoke results recorded before this correction are local evidence only.
- Hosted environment proof, deployed external smoke, and deployed clean-context UI acceptance remain incomplete.
- No production completion claim is valid until source requirements, strict hosted readiness, deployed smoke, and clean-context UI acceptance all pass.
- 2026-06-29 cleanup verification: `python -m py_compile` on changed backend/test files; `uv run ruff check backend/src/sextant/infra/source_pipeline.py backend/src/sextant/skills/local_memory_extractor.py backend/tests/integration/test_source_pipeline_cleanup.py backend/tests/golden/test_provider_golden.py`; `uv run pytest -q backend/tests/integration/test_source_pipeline_cleanup.py backend/tests/golden/test_provider_golden.py backend/tests/integration/test_memory_writeback.py backend/tests/contract/test_prompt_registry.py -p no:tach` passed locally (`50 passed`); `git diff --check -- AGENTS.md PLAN.md README.md docs experience goals implementation web` passed locally.

## Implementation Checkpoint - 2026-07-01 - Story Skill Runtime, Real-Corpus Eval, and Retrieval Alignment

Completed in the live working tree:

- introduced first-class Story Skill runtime surfaces in `backend/src/sextant/ports/story_skills.py`, with `backend/src/sextant/infra/story_skill_registry.py` kept as a compatibility export; the runtime now owns registry metadata, resolver planning, `run_skill(...)`, and deterministic validator boundaries for `detect-pov`, `aggregate-events`, `derive-facts`, and `next-page-agent`;
- wired production paths to use the runtime where the layer contract allows it: `backend/src/sextant/infra/{memory_writeback.py,source_pipeline.py}` now execute provider-boundary skills through the shared runtime, while `backend/src/sextant/application/use_cases.py` records resolved skill plans and keeps deterministic story-draft validation aligned with the same contract boundary;
- implemented retrieval upgrades required by the source docs: `backend/src/sextant/infra/retrieval_fusion.py` adds reciprocal-rank fusion, `backend/src/sextant/infra/semantic_search.py` now preserves semantic match ref keys, and `backend/src/sextant/infra/uow.py` now applies RRF-based hybrid recall plus scene-local sliding-window style sampling;
- added real-corpus eval infrastructure without committing corpus text: `backend/src/sextant/infra/real_corpus_skill_eval.py`, `backend/scripts/real_corpus_memory_boundary_eval.py`, and `evals/datasets/real_corpus_memory_boundary/{fanren-chapter-slices.v1.json,codex-subagent-judge-rubric.v1.json}`.

Passed in the live working tree:

- `uv run --python /opt/homebrew/bin/python3 pytest backend/tests/integration/test_story_skill_runtime.py backend/tests/integration/test_real_corpus_skill_eval.py -q -p no:tach`
- `uv run --python /opt/homebrew/bin/python3 pytest backend/tests/integration/test_memory_answer_context_pack.py -q -p no:tach -k "semantic_recall or style_memory"`
- `uv run --python /opt/homebrew/bin/python3 pytest backend/tests/integration/test_story_draft_provider.py backend/tests/integration/test_agent_candidate_job.py backend/tests/integration/test_memory_writeback.py backend/tests/integration/test_source_pipeline_cleanup.py -q -p no:tach`
- `uv run --python /opt/homebrew/bin/python3 python -m py_compile backend/src/sextant/ports/story_skills.py backend/src/sextant/infra/story_skill_registry.py backend/src/sextant/infra/real_corpus_skill_eval.py backend/src/sextant/infra/retrieval_fusion.py backend/src/sextant/infra/semantic_search.py backend/src/sextant/infra/source_pipeline.py backend/src/sextant/infra/memory_writeback.py backend/src/sextant/infra/uow.py backend/src/sextant/application/use_cases.py`
- `uv run --python /opt/homebrew/bin/python3 python backend/scripts/real_corpus_memory_boundary_eval.py`

Observed results:

- targeted Story Skill runtime and eval coverage passed `9` focused tests before retrieval changes, then `11` focused tests after the retrieval additions;
- the dependent integration suite across story drafting, candidate jobs, writeback, and source-pipeline cleanup passed `72` tests after the runtime wiring;
- the real-corpus boundary eval passed all `3` Fanren chapter slices with `fact_count=0`, `thread_update_count=0`, `memory_page_count=0`, `review_item_count=0`, `graph_edge_count=0`, `source_span_count=1`, and `skill_run_count=1` for each case, proving the local provider path does not invent durable memory/canon side effects from arbitrary prose;
- local source-of-truth rows that previously remained `partial` for missing `SkillRegistry`, `Resolver`, `run_skill(...)`, RRF, sliding-window organization, and real-corpus eval are now implemented locally and should no longer be tracked as open repo work.

## Verification Checkpoint - 2026-07-01 - Full Local Verification And External Gate Recheck

Passed in the live working tree:

- `uv run --python /opt/homebrew/bin/python3 ruff check backend/src backend/tests backend/migrations backend/scripts`
- `uv run --python /opt/homebrew/bin/python3 ty check backend/src`
- `uv run --python /opt/homebrew/bin/python3 tach check`
- `uv run --python /opt/homebrew/bin/python3 semgrep --config .semgrep/sextant.yml backend/src --error --quiet`
- `uv run --python /opt/homebrew/bin/python3 pytest backend/tests`
- `pnpm --dir web lint`
- `pnpm --dir web typecheck`
- `pnpm --dir web build`
- `pnpm --dir web test`
- `pnpm --dir web test:e2e`
- `SEXTANT_DATABASE_URL=sqlite+pysqlite:////tmp/sextant-alembic-verify.sqlite uv run --python /opt/homebrew/bin/python3 alembic upgrade head`
- `uv run --python /opt/homebrew/bin/python3 python backend/scripts/generate_api_artifacts.py`
- `uv run --python /opt/homebrew/bin/python3 python backend/scripts/production_smoke.py`
- `uv run --python /opt/homebrew/bin/python3 python backend/scripts/real_corpus_memory_boundary_eval.py`
- `git diff --check -- AGENTS.md PLAN.md README.md docs experience goals implementation web`

Observed results:

- backend static checks, type checks, dependency layering, and Semgrep all passed;
- backend test suite passed `615` tests in `89.84s` with one external-library deprecation warning from `fastapi.testclient` / `starlette.testclient`;
- frontend lint, typecheck, production build, Vitest (`14` files / `106` tests), and Playwright (`6` scenarios) all passed after the Story Skill layer move to `ports/story_skills.py` and the e2e cleanup for the now-unused response JSON;
- Alembic upgrade reached head successfully using the documented SQLite override, API artifact generation completed without drift output, local `production_smoke.py` passed the real production-path smoke, and the real-corpus boundary eval again passed all `3` committed slice specs against the ignored Fanren corpus path.

External gate recheck:

- `bash scripts/validate-production-config.sh` still fails only on missing production configuration keys, not on code/runtime errors;
- `bash scripts/validate-hosted-readiness.sh --allow-blocked` still returns `hosted-readiness-blocked` with the exact missing deployment/proof refs now recorded in `docs/known-gaps.md`;
- the remaining repo-level blockers are therefore external hosted credentials, proof refs, deployed smoke, and deployed clean-context UI acceptance rather than additional local implementation work.

## Implementation Checkpoint - 2026-07-01 - Web Demo Fallback Is Explicit Opt-In

Completed in the live working tree:

- changed the workbench so missing API configuration renders a disconnected production state instead of automatically showing the seed-story demo workflow;
- added `VITE_SEXTANT_ENABLE_DEMO=true` as the explicit development opt-in for the no-API visual demo;
- updated `web/README.md` and `web/.env.example` so demo data cannot be mistaken for production behavior.

Passed in the live working tree:

- `pnpm --dir web test -- workbench-source-view.test.ts`
- `pnpm --dir web test -- workbench-demo-gate.test.tsx workbench-source-view.test.ts`
- `pnpm --dir web lint`
- `pnpm --dir web test`
- `pnpm --dir web typecheck`
- `pnpm --dir web build`
- `pnpm --dir web test:e2e`
- `git diff --check -- AGENTS.md PLAN.md README.md docs experience goals implementation web`
- `rg -n "TODO|TBD|[ \t]+$" AGENTS.md PLAN.md README.md docs experience goals implementation web || true`

Observed results:

- the source-view test failed before implementation because no-API mode returned the seed manuscript and title by default;
- the component-level demo-gate test failed before implementation because `Harbor Nine` still rendered without API config;
- after the fix, the focused Vitest run passed `15` files / `108` tests, full frontend Vitest passed `15` files / `108` tests, TypeScript passed, production build passed, and API-mode Playwright passed `6` scenarios;
- documentation diff check passed; the TODO/TBD scan only matched the documented command itself and the lockfile integrity string.

## Documentation Checkpoint - 2026-07-01 - Coverage Status Alignment And Hosted Gate Recheck

Completed in the live working tree:

- aligned the initial source coverage section with the later 2026-07-01 verification checkpoints so it no longer describes Story Skill runtime, RRF, sliding-window retrieval, API-mode UI, or local verification as still pending local work;
- updated `PLAN.md` so its historical target-documentation correction gate describes the then-current architecture gap as historical and keeps the current missing work limited to hosted proof, deployed smoke, clean-context UI acceptance, and other externally evidenced hosted release gates.

Passed in the live working tree:

- `git diff --check -- AGENTS.md PLAN.md README.md docs experience goals implementation web`
- `rg -n "TODO|TBD|[ \t]+$" AGENTS.md PLAN.md README.md docs experience goals implementation web || true`
- targeted stale-status `rg` scan over progress, readiness, gaps, decisions, README, PLAN, web README, and acceptance-matrix docs

External gate recheck:

- `bash scripts/validate-production-config.sh` still failed only because required production configuration variables are absent from the local environment;
- `bash scripts/validate-hosted-readiness.sh --allow-blocked` returned `hosted-readiness-blocked` and listed the same missing hosted configuration, deployment identity, managed data-plane proof, secret/session/invitation proof, observability/capacity proof, hosted semantic/DR proof, and deployed acceptance proof refs already tracked in `docs/known-gaps.md`;
- no new local implementation blocker was identified in this checkpoint.

## Deployment Checkpoint - 2026-07-01 - VPS SSH And Supabase Postgres

Completed in the live deployment environment:

- provisioned the new BandwagonHost VPS as Ubuntu 24.04.4 LTS and verified dedicated SSH key access to `74.211.103.250`;
- created Supabase project `sextant-prod` with project ref `ientixxmbdeoqdmkublx` in `us-west-1`;
- verified direct hosted PostgreSQL connectivity to Supabase Postgres 17.6 without printing the connection string or password;
- enabled pgvector in Supabase and verified vector extension version `0.8.0`;
- fixed Alembic environment handling for percent-encoded database URLs and added regression coverage;
- ran Alembic migrations against Supabase and verified head `9e0f1a2b3c4d`, `39` base tables, and pgvector availability.

Passed in the live working tree:

- `uv run pytest backend/tests/integration/test_migrations.py::test_alembic_env_accepts_percent_encoded_database_url -q` failed before the fix with the same ConfigParser interpolation error observed in the Supabase migration attempt;
- `uv run pytest backend/tests/integration/test_migrations.py -q` passed after the fix (`2 passed`);
- Supabase migration verification printed `SUPABASE_ALEMBIC_OK`, `alembic_version=9e0f1a2b3c4d`, `base_table_count=39`, and `vector_extversion=0.8.0`.

Remaining hosted work after this checkpoint:

- Cloudflare R2 object storage, DNS/TLS, secret/session proof, deployed API/worker, Vercel frontend, provider live eval, external smoke, pgvector recall data proof, DR/rollback proof, observability proof, and browser-based clean-context acceptance are still not complete.

## Deployment Checkpoint - 2026-07-01 - Cloudflare R2 WNAM Object Store

Completed in the live deployment environment:

- deleted the unused APAC `sextant-prod-objects` R2 bucket before production data was written;
- created replacement R2 bucket `sextant-prod-wnam-objects` with Cloudflare location hint `WNAM`;
- verified the Cloudflare bucket settings page reports `位置：北美洲西部 (WNAM)`;
- created a new scoped R2 Account API token for `sextant-prod-wnam-objects` with object read/write access;
- updated local production secrets outside the repository in `~/.sextant-prod/secrets.env` with the new bucket, endpoint, token, S3 access key, and S3 secret key without printing secret values.

Passed against the live R2 bucket:

- `SEXTANT_OBJECT_STORE_ROOT=s3://sextant-prod-wnam-objects/objects uv run python backend/scripts/hosted_object_store_probe.py > /tmp/sextant-r2-wnam-probe.json`

Observed results:

- the hosted object-store probe returned `status=pass`;
- the sanitized proof recorded `object_store_root=s3://sextant-prod-wnam-objects/objects`;
- the sanitized proof recorded `s3_endpoint_host=90e8f098f1c4dc0c6cfbbdd4f03c4248.r2.cloudflarestorage.com`;
- the sanitized proof recorded `probe_prefix=hosted-readiness/object-store`, `byte_count=129`, and payload SHA-256 `35fb8391821636543126de7799fdec30b26c9896ccd520b783938622436695ca`.
- after user requested prioritizing US locality before continuing deployment, reran the hosted object-store probe against `s3://sextant-prod-wnam-objects/objects`; the probe returned `status=pass`, `byte_count=129`, and payload SHA-256 `7408f0d821199f54f07a71409d01660f2093236ca0f51c761801bc2b1684248e`.

Remaining hosted work after this checkpoint:

- Cloudflare DNS/TLS, secret/session proof, deployed API/worker, Vercel frontend, provider live eval, external smoke, pgvector recall data proof, DR/rollback proof, observability proof, and browser-based clean-context acceptance are still not complete.

## Deployment Checkpoint - 2026-07-01 - Hosted API, Worker, Provider, And Vector Proof

Completed in the live deployment environment:

- deployed the production API behind `https://api.sextantlabs.net` with Caddy-managed HTTPS and Cloudflare DNS-only A record to VPS `74.211.103.250`;
- deployed the production worker as `sextant-worker.service` on the VPS and verified the worker processes the hosted job chain through `run_memory_writeback`;
- fixed the SQLAlchemy source import flush ordering so `SourceVersion` is inserted before the referencing `SourceDelta`;
- fixed the OpenAI memory extraction structured-output contract so `facts[].predicate` is constrained to the base story-schema relation enum instead of arbitrary provider strings;
- updated the OpenAI memory extraction prompt lock and reran prompt/provider tests after the schema change;
- added Alembic revision `af1b2c3d4e5f` to create the pgvector HNSW index for the configured hosted embedding dimension, then upgraded Supabase to that head.

Passed in the live working tree:

- `uv run pytest backend/tests/integration/test_application_use_cases.py::test_create_source_inserts_version_before_delta_reference -q`
- `uv run pytest backend/tests/integration/test_api_contracts.py::test_source_schema_write_endpoints_persist_expected_success_side_effects -q`
- `uv run pytest backend/tests/integration/test_memory_extraction_provider.py backend/tests/contract/test_prompt_registry.py -q`
- `uv run pytest backend/tests/integration/test_migrations.py backend/tests/integration/test_hosted_pgvector_recall_probe.py -q`

Passed against hosted production services:

- `curl -sk --max-time 20 https://api.sextantlabs.net/health`
- `uv run python backend/scripts/hosted_external_smoke.py`
- `SEXTANT_HOSTED_WORKER_METRICS_URL=https://api.sextantlabs.net/worker-metrics uv run python backend/scripts/hosted_worker_capacity_probe.py`
- `uv run python backend/scripts/hosted_provider_live_eval_probe.py`
- `SEXTANT_PGVECTOR_RECALL_PROJECT_ID=fc5d58ab-80bd-4761-adef-3593cc98c756 uv run python backend/scripts/hosted_pgvector_recall_probe.py`

Observed results:

- hosted API health returned `status=ok`, `service=sextant-api`, `release_environment=production`, and deployment version `2026.07.01+vps.74.211.103.250`;
- hosted external smoke returned `status=pass`, `job_status=succeeded`, `evidence_log_count=1`, `fact_count=1`, `graph_edge_count=1`, `memory_page_count=1`, and `memory_answer_source_span_count=1`;
- worker metrics showed all 9 hosted smoke job types succeeded, including `run_memory_writeback`, with no terminal failures in the capacity probe;
- provider live eval returned `status=pass` for `embedding`, `event_aggregation`, `memory_extraction`, `pov_detection`, and `story_draft`;
- Supabase project discovery through the Supabase connector returned project `sextant-prod`, ref `ientixxmbdeoqdmkublx`, region `us-west-1`, status `ACTIVE_HEALTHY`, and PostgreSQL `17.6.1.127`;
- Supabase Alembic state advanced to `af1b2c3d4e5f`; `ix_semantic_embeddings_embedding_vector_hnsw` now exists as an HNSW index over `embedding_vector::vector(1024)` where `dimensions = 1024`;
- semantic embedding refresh for the hosted smoke project wrote `1` memory-page vector, `3` source-span vectors, and `3` style-sample vectors using `openai/text-embedding-v4` at `1024` dimensions;
- hosted pgvector recall returned `status=pass`, `vector_rows=7`, `hnsw_index=ix_semantic_embeddings_embedding_vector_hnsw`, and `nearest_distance=0.0`.

Remaining hosted work after this checkpoint:

- Vercel frontend deployment, deployed clean-context UI acceptance, source-delta search reindex proof, secret/session/invitation proof, observability pipeline proof, backup/restore proof, rollback execution proof, and final hosted-readiness gate alignment remain incomplete.

## Deployment Checkpoint - 2026-07-01 - Runtime Frontend Auth Boundary

Completed in the live working tree:

- added a runtime Supabase Auth boundary for hosted Vite deployments so production does not require or allow a bundled `VITE_SEXTANT_BEARER_TOKEN`;
- added a Workbench login gate that appears when API context and Supabase Auth public config are present but no runtime JWT exists;
- added local session storage for returned Supabase access tokens without storing author passwords;
- updated `web/.env.example` and `web/README.md` to separate local/manual bearer-token use from hosted runtime login.

Passed in the live working tree:

- `pnpm --dir web test -- tests/workbench-api.test.ts tests/workbench-demo-gate.test.tsx` first failed on missing `readWorkbenchAuthConfig`, missing `signInWorkbenchWithPassword`, and missing login gate;
- after implementation, `pnpm --dir web test -- tests/workbench-api.test.ts tests/workbench-demo-gate.test.tsx` passed (`15` files / `111` tests);
- `pnpm --dir web typecheck` passed;
- `pnpm --dir web lint` passed.

Observed results:

- `web/lib/workbench-api.ts` now exchanges credentials against `${VITE_SEXTANT_SUPABASE_URL}/auth/v1/token?grant_type=password` using the public publishable key;
- `web/components/workbench/index.tsx` does not enter the API workbench when Supabase Auth runtime config is present and no bearer token exists;
- `web/.env.example` marks `VITE_SEXTANT_BEARER_TOKEN` as local/manual only and adds `VITE_SEXTANT_SUPABASE_URL` plus `VITE_SEXTANT_SUPABASE_PUBLISHABLE_KEY`.

Remaining hosted work after this checkpoint:

- new Vercel frontend deployment, backend CORS alignment for the Vercel/app origin, browser clean-context login and workflow acceptance, source-delta search reindex proof, secret/session/invitation proof refs, observability pipeline proof, backup/restore proof, rollback execution proof, and final hosted-readiness gate alignment remain incomplete.

## Deployment Checkpoint - 2026-07-01 - Vercel Frontend And Hosted UI Writeback

Completed in the live deployment environment:

- deleted the stale Vercel project `sextant-v3-web` and verified the Vercel connector no longer listed it;
- created the new Vercel project `sextant-web` under `frankqdwang1-9171s-projects`;
- deployed the hosted Vite workbench to `https://sextant-web-nine.vercel.app` without a bundled bearer token;
- configured the backend CORS allowlist on the VPS for the Vercel production alias and immutable deployment URL;
- fixed the OpenAI memory extraction structured-output contract a second time so relation-specific subject/object roles are enforced in the provider schema, not only by downstream validation;
- uploaded the relation-role schema and prompt-lock fix to the VPS, verified the remote import path and schema, and restarted `sextant-api` plus `sextant-worker`.

Passed in the live working tree:

- `uv run pytest backend/tests/integration/test_memory_extraction_provider.py::test_openai_memory_extraction_structured_schema_limits_relation_roles -q` first failed because the old schema had no relation-specific `oneOf` branch for `facts`;
- after implementation, `uv run pytest backend/tests/integration/test_memory_extraction_provider.py -q` passed (`14 passed`);
- `uv run pytest backend/tests/integration/test_memory_extraction_provider.py backend/tests/contract/test_prompt_registry.py -q` passed (`16 passed`);
- `pnpm --dir web build` passed with hosted API/Supabase public auth configuration and `VITE_SEXTANT_BEARER_TOKEN` blank.

Passed against hosted production services:

- `curl -sk https://api.sextantlabs.net/health`;
- hosted CORS preflight from origin `https://sextant-web-nine.vercel.app`;
- remote VPS schema verification using `PYTHONPATH=/opt/sextant/current/backend/src` and `SEXTANT_PROMPT_ROOT=/opt/sextant/current/prompts`;
- browser-based production UI workflow at `https://sextant-web-nine.vercel.app`.

Observed results:

- Vercel production deployment `dpl_4QoHJ1SQWJwnJmFciuH7BCNmgcsJ` was ready and aliased as `https://sextant-web-nine.vercel.app`;
- API health returned `status=ok`, `service=sextant-api`, `release_environment=production`, and deployment version `2026.07.01+vps.74.211.103.250`;
- CORS preflight returned `access-control-allow-origin: https://sextant-web-nine.vercel.app`;
- remote schema verification returned `REMOTE_FACT_BRANCHES=29`, `REMOTE_OWNS_OBJECT_TYPE=object`, and prompt hash `f14d85ff23d79f119eb55dae6385bb7614deed2c60242af5f56b3a839fc6e74a`;
- browser UI login used Supabase Auth runtime credentials, then loaded `Hosted smoke chapter` from the hosted API at source version `hosted-smoke+1`;
- browser UI memory checks showed hosted memory page/graph evidence for `Mira -> Lantern Map`, a negative evidence-boundary answer for an unsupported POV question, and a positive answer for `Mira 持有什么？`;
- browser UI candidate acceptance created source version `hosted-smoke+2`, displayed `回写任务 · 完成`, and showed a reviewable evidence span in the Memory Writeback drawer;
- Supabase Postgres confirmed the latest `run_memory_writeback` job `7fac172d-a503-4fc2-a61e-a82edc6c7247` succeeded with `last_error=null`, SourceDelta `0238c2af-1e36-4d4d-bc59-e90c6dff1176` reached `memory_writeback_completed`, and the resulting version had `2` source spans, `2` evidence-log references, and `2` memory-page refs.

The failed hosted UI writeback immediately before this fix remains useful negative evidence:

- job `1c5fd18d-2e7b-4076-a4fe-076f3f41f265` failed terminal with `llm_output_invalid: Memory extraction provider returned schema-invalid fact: schema_relation_role_not_allowed`;
- the accepted fix did not loosen deterministic validation and instead constrained provider output through the structured schema and prompt.

Remaining hosted work after this checkpoint:

- persist/align Vercel production environment proof refs, configure the final `app.sextantlabs.net` domain if required by acceptance, run the full hosted verification sweep again after the relation-role deploy, complete source-delta search reindex proof, secret/session/invitation proof refs, observability pipeline proof, backup/restore proof, rollback execution proof, and final hosted-readiness gate alignment.

## Deployment Checkpoint - 2026-07-01 - Hosted Reindex Proof And S3 Timeout Bounds

Completed in the live working tree:

- fixed `reindex_source_delta_search(..., rebuild_all=True)` so full rebuild mode advances by `(created_at, id)` cursor pagination instead of repeatedly selecting the same first batch;
- added bounded S3-compatible object-store client configuration with `SEXTANT_S3_CONNECT_TIMEOUT_SECONDS`, `SEXTANT_S3_READ_TIMEOUT_SECONDS`, and `SEXTANT_S3_MAX_ATTEMPTS`;
- updated `.env.example`, `README.md`, and `docs/deployment-runbook.md` with the timeout env vars and `hosted_source_delta_reindex_probe.py --all` proof mode.

Passed in the live working tree:

- `uv run pytest backend/tests/integration/test_source_delta_reindex.py::test_reindex_source_delta_search_rebuild_all_advances_batches -q` first failed because old `--all` mode repeated the first SourceDelta batch;
- after implementation, `uv run pytest backend/tests/integration/test_source_delta_reindex.py backend/tests/unit/test_object_store.py -q` passed (`5 passed`);
- `uv run pytest backend/tests/unit/test_object_store.py -q` passed after asserting default S3 connect/read timeout and retry bounds.

Passed against hosted production services:

- `uv run python backend/scripts/hosted_source_delta_reindex_probe.py --batch-size 50` returned `status=pass`, `rebuild_all=false`, and `reindexed_rows=0`;
- `SEXTANT_S3_CONNECT_TIMEOUT_SECONDS=5 SEXTANT_S3_READ_TIMEOUT_SECONDS=5 SEXTANT_S3_MAX_ATTEMPTS=1 uv run python backend/scripts/hosted_source_delta_reindex_probe.py --batch-size 20 --all` returned `status=pass`, `rebuild_all=true`, and `reindexed_rows=5`;
- VPS deployment of `backend/src/sextant/infra/object_store.py` and `backend/src/sextant/infra/source_delta_search.py` was followed by `systemctl restart sextant-api sextant-worker`, both active;
- remote import verification returned `REMOTE_S3_TIMEOUTS=(7.0, 11.0, 3)`, proving the deployed VPS code loads bounded S3 client config.

Observed results:

- Supabase/R2 SourceDelta object refs all resolved through `s3://sextant-prod-wnam-objects/objects/...`;
- the full hosted reindex proof sanitized the database URL and reported `database_host=aws-1-us-west-1.pooler.supabase.com`, `object_store_root=s3://sextant-prod-wnam-objects/objects`, and `reindexed_rows=5`;
- this closes the live SourceDelta search reindex execution proof, but the final auditable `SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF` still needs to be recorded for the hosted-readiness gate.

Remaining hosted work after this checkpoint:

- persist/align Vercel and reindex proof refs, configure the final `app.sextantlabs.net` domain if required by acceptance, complete secret/session/invitation proof refs, observability pipeline proof, backup/restore proof, rollback execution proof, and final hosted-readiness gate alignment.

## Deployment Checkpoint - 2026-07-01 - Final App Domain

Completed in the live deployment environment:

- added `app.sextantlabs.net` to the Vercel `sextant-web` project;
- used Vercel Domain Connect with the logged-in Cloudflare account to add DNS-only Cloudflare records for the Vercel target;
- explicitly aliased deployment `sextant-3l1hbh706-frankqdwang1-9171s-projects.vercel.app` to `app.sextantlabs.net`;
- persisted production Vercel env vars for the hosted Vite app without setting `VITE_SEXTANT_BEARER_TOKEN`;
- redeployed from the Vercel project production env so the deployment is reproducible without local one-off build env flags;
- updated API CORS for `https://app.sextantlabs.net` and the new immutable deployment URL;
- verified the final domain through Vercel CLI and browser-based production UI login.

Passed against hosted production services:

- `pnpm dlx vercel domains verify app.sextantlabs.net --scope frankqdwang1-9171s-projects` returned `status=ok`, `reason=configured_correctly`, `configuredBy=CNAME`, and `project.verified=true`;
- `pnpm dlx vercel alias set sextant-3l1hbh706-frankqdwang1-9171s-projects.vercel.app app.sextantlabs.net --scope frankqdwang1-9171s-projects` returned success;
- `pnpm dlx vercel deploy . --prod --yes --project sextant-web --scope frankqdwang1-9171s-projects --force` returned deployment `dpl_pQBgcTNB7s8XoSmbk2FjvDbYJUYv`, ready state `READY`, and alias `https://app.sextantlabs.net`;
- hosted CORS preflights returned `access-control-allow-origin` for both `https://app.sextantlabs.net` and `https://sextant-l4n3ki70w-frankqdwang1-9171s-projects.vercel.app`;
- direct HTTPS checks using Vercel edge IPs `216.198.79.65` and `64.29.17.65` returned HTTP `200`;
- Chrome loaded `https://app.sextantlabs.net/`, showed the runtime Supabase login gate, logged in with the smoke author account, loaded `Hosted smoke chapter` at `hosted-smoke+2`, and opened the Memory Page drawer with `Mira` evidence for `Lantern Map`.

Observed results:

- Cloudflare Domain Connect showed it would add TXT `_vercel` plus DNS-only CNAME `app -> fce134efe3e4ccca.vercel-dns-017.com`;
- Vercel verify reported current CNAME `fce134efe3e4ccca.vercel-dns-017.com.`;
- Vercel production env now contains public Vite configuration for API URL, project/source IDs, Supabase project URL, and Supabase publishable key; it intentionally does not contain a frontend bearer token;
- the production frontend continues to use runtime Supabase Auth and does not require a bundled bearer token on the final app domain.

Remaining hosted work after this checkpoint:

- persist/align deployment, clean-context acceptance, external smoke, worker/provider/pgvector/reindex proof refs; complete managed secret-manager proof, session-provider/invitation/token-issuer proof, observability pipeline proof, backup/restore proof, rollback execution proof, and final hosted-readiness gate alignment.

## Verification Checkpoint - 2026-07-01 - Hosted Gate Status After Domain/Reindex

Passed in the live working tree:

- `uv run pytest backend/tests/integration/test_source_delta_reindex.py backend/tests/unit/test_object_store.py backend/tests/integration/test_memory_extraction_provider.py backend/tests/contract/test_prompt_registry.py -q` passed (`21 passed`);
- `pnpm --dir web test` passed (`15` files / `111` tests);
- `pnpm --dir web typecheck` passed;
- `pnpm --dir web lint` passed;
- production `pnpm --dir web build` passed with hosted API/Supabase public auth config and no bearer token;
- `git diff --check -- AGENTS.md PLAN.md README.md docs experience goals implementation web backend prompts evals .env.example` passed;
- `bash scripts/validate-production-config.sh` returned `production-config-ok`.

Passed against hosted production services after the final domain/redeploy:

- hosted external smoke using a temporary Supabase Auth JWT returned `status=pass`, job `86c0f939-8be8-4eb9-9863-77d49f365910`, `job_status=succeeded`, `evidence_log_count=1`, `fact_count=1`, `graph_edge_count=1`, `memory_page_count=1`, and `memory_answer_source_span_count=2`;
- worker capacity probe returned `status=pass`, `failed_terminal_jobs=0`, `succeeded_jobs=9.0`, and `metric_series_count=30`;
- provider live eval returned `status=pass` for `embedding`, `event_aggregation`, `memory_extraction`, `pov_detection`, and `story_draft`;
- pgvector recall returned `status=pass`, `vector_rows=7`, and HNSW index `ix_semantic_embeddings_embedding_vector_hnsw`;
- SourceDelta full reindex returned `status=pass`, `rebuild_all=true`, and `reindexed_rows=5`;
- browser UI at `https://app.sextantlabs.net/` loaded after redeploy and displayed the hosted source plus runtime context.

Hosted-readiness gate result:

- `bash scripts/validate-hosted-readiness.sh --allow-blocked` still returns `hosted-readiness-blocked`;
- remaining missing refs/config are exact external proof items: `SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF`, `SEXTANT_OBJECT_STORE_IAM_PROOF_REF`, `SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF`, `SEXTANT_SECRET_MANAGER_REF`, `SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF`, `SEXTANT_SESSION_PROVIDER_ADMIN_URL`, `SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF`, `SEXTANT_INVITATION_DELIVERY_PROVIDER`, `SEXTANT_INVITATION_DELIVERY_PROOF_REF`, `SEXTANT_TOKEN_ISSUER_PROOF_REF`, `SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF`, `SEXTANT_WORKER_CAPACITY_PROOF_REF`, `SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF`, `SEXTANT_PGVECTOR_RECALL_PROOF_REF`, `SEXTANT_BACKUP_RESTORE_PROOF_REF`, `SEXTANT_ROLLBACK_RUNBOOK_REF`, `SEXTANT_ROLLBACK_EXECUTION_PROOF_REF`, `SEXTANT_EXTERNAL_SMOKE_PROOF_REF`, `SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF`, and `SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF`;
- these must not be filled with fake refs. Some have live evidence in this log and need auditable artifact/ref alignment; managed secret manager, invitation delivery provider, observability traces/alerts, scratch restore database, and rollback execution still require real external setup.

## Deployment Checkpoint - 2026-07-01 - Production-Ready TODO Policy

Completed in the live working tree:

- added root `TODOs.md` to track production-readiness work that is explicitly incomplete and must not be reported as done;
- recorded the deployment dependency decision that remaining readiness work should use Supabase, Vercel, VPS, and Cloudflare first, without adding AWS/GCP/Vault, external email providers, or third-party observability billing unless later approved;
- clarified that invitation delivery is deferred until the real launch domain and user onboarding plan are known, while remaining a readiness item if required by the source documents;
- clarified that backup/restore means restoring production data into a separate scratch Supabase project or database so restore safety can be proven without mutating production;
- clarified that rollback proof means executing a real Vercel rollback or alias-rollback drill and restoring the current production deployment with exact evidence.

Observed results:

- this checkpoint changes documentation and acceptance tracking only; it does not close the hosted-readiness gate;
- the remaining items are now split between proof-ref alignment for already-passed hosted checks and real external work for secret management, invitation delivery, observability, backup/restore, rollback, R2 IAM, and session-provider proof.

## Deployment Checkpoint - 2026-07-01 - Supabase Vault Secret-Manager Path

Completed in the live working tree:

- added `supabase-vault://<project-ref>/<secret-name>` support to provider secret resolution, hosted secret-manager proof, hosted provider live eval credential gating, production config validation, and hosted readiness validation;
- added TDD coverage for provider resolver behavior, hosted secret-manager probe redaction, provider-live-eval credential-source policy, and shell gate acceptance;
- created production Supabase Vault secret `sextant_openai_api_key` in project `ientixxmbdeoqdmkublx` without printing the secret value;
- updated root `TODOs.md`, `docs/known-gaps.md`, and `docs/implementation-decisions.md` so the current VPS env file is not misreported as a managed secret manager.

Passed in the live working tree:

- `uv run pytest backend/tests/integration/test_provider_secrets.py backend/tests/integration/test_hosted_secret_manager_probe.py backend/tests/integration/test_production_config_gate.py -q` passed (`23 passed`);
- `uv run pytest backend/tests/integration/test_hosted_provider_live_eval_probe.py -q` passed (`5 passed`);
- `bash scripts/validate-production-config.sh` passed with `OPENAI_API_KEY` and `SEXTANT_OPENAI_API_KEY` unset and `SEXTANT_LLM_API_KEY_SECRET_REF=supabase-vault://ientixxmbdeoqdmkublx/sextant_openai_api_key`;
- `backend/scripts/hosted_secret_manager_probe.py` returned `status=pass`, `secret_ref_scheme=supabase-vault`, and redacted hash/byte-count evidence;
- `backend/scripts/hosted_provider_live_eval_probe.py` returned `status=pass` with `credential_source=supabase-vault` and all five provider skills passing.

Observed results:

- production Supabase confirmed `supabase_vault` extension `0.3.1` is installed and `vault` schema exists;
- the new hosted-readiness run with `SEXTANT_SECRET_MANAGER_REF=supabase-vault://ientixxmbdeoqdmkublx/sextant_openai_api_key` and `SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF=runbook://supabase-vault/sextant-openai-api-key` no longer listed secret-manager env vars as missing;
- KiwiVM shell access was blocked by an expired KiwiVM session, so VPS API/worker runtime has not yet been switched to the Supabase Vault ref.

Remaining hosted work after this checkpoint:

- deploy the Supabase Vault resolver/probe changes to the VPS, update `/etc/sextant/sextant.env` to use the Supabase Vault secret ref instead of a direct runtime OpenAI key, restart `sextant-api` and `sextant-worker`, and rerun VPS-side production/provider verification.

## Deployment Checkpoint - 2026-07-01 - Vercel Alias Rollback Drill

Completed against hosted Vercel production:

- recorded current `app.sextantlabs.net` deployment before the drill as `dpl_pQBgcTNB7s8XoSmbk2FjvDbYJUYv`, URL `https://sextant-l4n3ki70w-frankqdwang1-9171s-projects.vercel.app`;
- executed real alias rollback with `pnpm dlx vercel alias set sextant-3l1hbh706-frankqdwang1-9171s-projects.vercel.app app.sextantlabs.net --scope frankqdwang1-9171s-projects`;
- verified rollback target `dpl_4QoHJ1SQWJwnJmFciuH7BCNmgcsJ`, URL `https://sextant-3l1hbh706-frankqdwang1-9171s-projects.vercel.app`, status `Ready`;
- verified `https://app.sextantlabs.net/` returned HTTP `200` while pointed at the rollback target;
- restored current production with `pnpm dlx vercel alias set sextant-l4n3ki70w-frankqdwang1-9171s-projects.vercel.app app.sextantlabs.net --scope frankqdwang1-9171s-projects`;
- verified final `vercel inspect app.sextantlabs.net --scope frankqdwang1-9171s-projects` resolved back to `dpl_pQBgcTNB7s8XoSmbk2FjvDbYJUYv`;
- verified final `https://app.sextantlabs.net/` returned HTTP `200`.

Observed results:

- rollback precheck timestamp was `2026-07-01T07:53:07Z`;
- final restore verification timestamp was `2026-07-01T07:53:49Z`;
- the app domain was left on the current deployment, not the rollback target.

Remaining hosted work after this checkpoint:

- align `SEXTANT_ROLLBACK_RUNBOOK_REF` and `SEXTANT_ROLLBACK_EXECUTION_PROOF_REF` to this progress-log evidence, and run any separate backend/VPS rollback drill if later required by source acceptance.

## Verification Checkpoint - 2026-07-01 - Hosted Proof-Ref Alignment

Completed in the local production env:

- set non-sensitive `runbook://docs/progress-log/...` proof refs for deployment approval, object-store read/write, worker capacity, provider live eval, pgvector recall, external smoke, clean-context UI acceptance, SourceDelta search reindex, Vercel rollback runbook, and Vercel rollback execution;
- set `SEXTANT_SECRET_MANAGER_REF=supabase-vault://ientixxmbdeoqdmkublx/sextant_openai_api_key` and `SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF=runbook://docs/progress-log/supabase-vault-secret-manager-path`;
- did not set proof refs for object-store IAM, session provider, invitation delivery, token issuer, observability, or backup/restore because those still need separate evidence.

Passed:

- `set -a; source ~/.sextant-prod/secrets.env; set +a; bash scripts/validate-hosted-readiness.sh --allow-blocked` returned `hosted-readiness-blocked` with the missing list reduced to `SEXTANT_OBJECT_STORE_IAM_PROOF_REF`, `SEXTANT_SESSION_PROVIDER_ADMIN_URL`, `SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF`, `SEXTANT_INVITATION_DELIVERY_PROVIDER`, `SEXTANT_INVITATION_DELIVERY_PROOF_REF`, `SEXTANT_TOKEN_ISSUER_PROOF_REF`, `SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF`, and `SEXTANT_BACKUP_RESTORE_PROOF_REF`.

Observed results:

- secret-manager, rollback, provider live eval, pgvector, external smoke, clean-context UI, worker capacity, object read/write, and reindex proof refs no longer appear in the hosted-readiness missing list;
- remaining blockers now represent real unproven system/infrastructure work, not local proof-ref bookkeeping.

## Deployment Checkpoint - 2026-07-01 - Supabase Auth Session And Token Proof

Completed in the live working tree:

- added `supabase://<project-ref>/auth` as an accepted proof-ref scheme for session-provider provisioning and token-issuer proof paths;
- added public, sanitized readiness artifacts under `web/public/readiness/` for Supabase Auth provisioning and token issuance;
- deployed Vercel production deployment `dpl_CD5WNMNrYXySwyMa6FxciEpChzzS`, URL `https://sextant-1cgpvos1i-frankqdwang1-9171s-projects.vercel.app`, aliased to `https://app.sextantlabs.net`;
- updated local production env with `SEXTANT_SESSION_PROVIDER_ADMIN_URL=https://supabase.com/dashboard/project/ientixxmbdeoqdmkublx/auth/users`, `SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF=supabase://ientixxmbdeoqdmkublx/auth`, and `SEXTANT_TOKEN_ISSUER_PROOF_REF=supabase://ientixxmbdeoqdmkublx/auth`.

Passed in the live working tree:

- `uv run pytest backend/tests/integration/test_hosted_session_provider_provisioning_probe.py backend/tests/integration/test_hosted_token_issuer_probe.py -q` passed (`9 passed`);
- `uv run pytest backend/tests/integration/test_production_config_gate.py::test_hosted_readiness_gate_records_external_blockers_without_faking_success -q` passed;
- `pnpm --dir web build` passed;
- `git diff --check -- web/public/readiness/session-provider-provisioning.json web/public/readiness/token-issuer.json backend/scripts/hosted_session_provider_provisioning_probe.py backend/scripts/hosted_token_issuer_probe.py backend/scripts/hosted_session_provider_probe.py scripts/validate-hosted-readiness.sh backend/tests/integration/test_hosted_session_provider_provisioning_probe.py backend/tests/integration/test_hosted_token_issuer_probe.py backend/tests/integration/test_production_config_gate.py` passed.

Passed against hosted production services:

- `curl -sk https://app.sextantlabs.net/readiness/session-provider-provisioning.json` returned provider `supabase`, issuer `https://ientixxmbdeoqdmkublx.supabase.co/auth/v1`, JWKS URL, admin URL, `status=provisioned`, `client_count=1`, and `jwks_key_count=1`;
- `curl -sk https://app.sextantlabs.net/readiness/token-issuer.json` returned issuer `https://ientixxmbdeoqdmkublx.supabase.co/auth/v1`, audience `authenticated`, `status=issued`, `token_count=1`, `subject_count=1`, and one subject hash;
- `uv run python backend/scripts/hosted_session_provider_provisioning_probe.py` returned `status=pass`, `provider=supabase`, `provisioning_status=provisioned`, `client_count=1`, and artifact hash `7e298bcd4a354047d75efed87d41e035b447fa383a5795fe4fa943e28bd57d33`;
- `uv run python backend/scripts/hosted_token_issuer_probe.py` returned `status=pass`, `issuance_status=issued`, `token_count=1`, `subject_count=1`, and artifact hash `60ad365afc4d94347d892e30d0063b9d0486dfd19ffce2ab7d3a9ea9bab383cf`;
- `bash scripts/validate-hosted-readiness.sh --allow-blocked` now reports only five missing values: `SEXTANT_OBJECT_STORE_IAM_PROOF_REF`, `SEXTANT_INVITATION_DELIVERY_PROVIDER`, `SEXTANT_INVITATION_DELIVERY_PROOF_REF`, `SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF`, and `SEXTANT_BACKUP_RESTORE_PROOF_REF`.

Observed results:

- Supabase JWKS returned one ES256 signing key;
- Supabase password-token issuance for the smoke author returned an access token and user id, but only token count, subject count, and a subject hash were recorded;
- invitation delivery remains explicitly incomplete because no launch domain/user onboarding provider is configured yet.

## Deployment Checkpoint - 2026-07-01 - Cloudflare R2 IAM Proof

Completed in the live working tree:

- added `cloudflare-r2://` as an accepted object-store IAM proof-ref scheme for hosted readiness and `hosted_object_store_iam_probe.py`;
- added TDD coverage for Cloudflare R2 artifact acceptance and hosted-readiness gate validation;
- published sanitized Cloudflare R2 IAM evidence at `https://app.sextantlabs.net/readiness/object-store-iam.json`;
- set local production env proof refs to `SEXTANT_OBJECT_STORE_IAM_PROOF_REF=cloudflare-r2://sextant-prod-wnam-objects/runtime-token` and `SEXTANT_OBJECT_STORE_IAM_ARTIFACT_URL=https://app.sextantlabs.net/readiness/object-store-iam.json`.

Passed in the live working tree:

- `uv run pytest backend/tests/integration/test_hosted_object_store_iam_probe.py backend/tests/integration/test_production_config_gate.py::test_hosted_readiness_gate_records_external_blockers_without_faking_success -q` passed (`6 passed`);
- `pnpm --dir web build` passed;
- `git diff --check -- TODOs.md web/public/readiness/object-store-iam.json backend/scripts/hosted_object_store_iam_probe.py scripts/validate-hosted-readiness.sh backend/tests/integration/test_hosted_object_store_iam_probe.py backend/tests/integration/test_production_config_gate.py docs/progress-log.md docs/known-gaps.md docs/implementation-decisions.md README.md docs/deployment-runbook.md` passed before the documentation status update.

Passed against hosted production services:

- Vercel deployment from the correct `web/` project directory produced production deployment `dpl_FqoYmLAPuGKNfgp8rwmrJJN1tPvd`, URL `https://sextant-cxkk26htb-frankqdwang1-9171s-projects.vercel.app`, aliased to `https://app.sextantlabs.net`;
- `curl -sk https://app.sextantlabs.net/readiness/object-store-iam.json` returned provider `cloudflare-r2`, bucket `sextant-prod-wnam-objects`, token name `sextant-prod-r2-runtime-wnam`, permission summary `Object Read & Write`, token status `active`, and bucket location `WNAM`;
- `uv run python backend/scripts/hosted_object_store_iam_probe.py` returned `status=pass`, `provider=cloudflare-r2`, `iam_status=attached`, `policy_statement_count=1`, `runtime_principal_count=1`, and artifact hash `4f13c6d39247b95b85755295ec82ba0238bbf4da8dc8e1f2de35026f4a6f22c4`;
- `bash scripts/validate-hosted-readiness.sh --allow-blocked` now reports only four missing values: `SEXTANT_INVITATION_DELIVERY_PROVIDER`, `SEXTANT_INVITATION_DELIVERY_PROOF_REF`, `SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF`, and `SEXTANT_BACKUP_RESTORE_PROOF_REF`.

Observed results:

- an initial Vercel deploy from the repository root produced `dpl_Eq7GJtjEE1YrzL1cpz82TmDLrCyf` but did not publish `web/public/readiness/*.json`; it was replaced by the correct `web/` directory deployment above;
- Cloudflare R2 dashboard evidence showed bucket `sextant-prod-wnam-objects` in WNAM, public development URL disabled, and active account token `sextant-prod-r2-runtime-wnam` scoped to object read/write for that bucket;
- object-store IAM is no longer a hosted-readiness missing value. Invitation delivery, observability pipeline, and backup/restore remain intentionally unproven rather than filled with fake refs.

## Implementation Checkpoint - 2026-07-01 - Self-Hosted Observability Surfaces

Completed in the live working tree:

- added `ObservabilityState` to record recent API trace samples with path templates, status, duration, and SHA-256 trace/span fingerprints only;
- added self-hosted API endpoints `GET /observability/traces` and `GET /observability/alerts`;
- wired alert state to real metrics counters, including API request errors and worker job failures, without adding Grafana Cloud, Prometheus SaaS, or an external OTel vendor;
- updated README and the deployment runbook to use the self-hosted API `/metrics`, `/observability/traces`, and `/observability/alerts` surfaces for the hosted observability pipeline probe.

Passed in the live working tree:

- new TDD tests first failed on missing endpoints, then `uv run pytest backend/tests/integration/test_api_contracts.py::test_observability_trace_endpoint_reports_sanitized_recent_api_activity backend/tests/integration/test_api_contracts.py::test_observability_alert_endpoint_reports_metric_derived_state_without_payloads -q` passed (`2 passed`);
- `uv run pytest backend/tests/integration/test_hosted_observability_pipeline_probe.py backend/tests/security/test_observability_redaction.py backend/tests/integration/test_runtime_app.py::test_runtime_app_assembles_real_uow_object_store_and_provider -q` passed (`12 passed`);
- `uv run pytest backend/tests/integration/test_api_contracts.py::test_api_request_observability_records_metrics_without_manuscript_text backend/tests/integration/test_api_contracts.py::test_api_trace_context_returns_safe_headers_and_log_fields backend/tests/integration/test_api_contracts.py::test_metrics_endpoint_exports_request_counters_without_manuscript_text backend/tests/integration/test_api_contracts.py::test_observability_trace_endpoint_reports_sanitized_recent_api_activity backend/tests/integration/test_api_contracts.py::test_observability_alert_endpoint_reports_metric_derived_state_without_payloads -q` passed (`5 passed`).

Observed hosted state:

- `curl -sk https://api.sextantlabs.net/metrics` returned HTTP `200` with `sextant_api_requests_total` and provider metrics from the current VPS API;
- `curl -sk https://api.sextantlabs.net/observability/traces` and `/observability/alerts` still returned HTTP `404` because the VPS runtime has not received the new API code;
- direct SSH to `root@74.211.103.250` still failed with `Connection timed out during banner exchange`, so VPS deployment and hosted observability proof remain blocked until KiwiVM/SSH access is restored.

Remaining hosted work after this checkpoint:

- deploy the new observability endpoint code to the VPS API, restart `sextant-api`, generate at least one API request so trace samples and metrics are present, run `hosted_observability_pipeline_probe.py` against `https://api.sextantlabs.net/metrics`, `/observability/traces`, and `/observability/alerts`, then set `SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF` to the archived evidence.

## Deployment Checkpoint - 2026-07-01 - Supabase Scratch Backup/Restore Proof

Completed against hosted production services:

- created Supabase scratch project `avjwnxdexbwdenipizfc` (`sextant-restore-proof-scratch`) in org `lepnqbpwtaqptrwiuwgt`, region `us-west-1`, with project cost reported by Supabase MCP as `$0/month`;
- configured the scratch restore database URL outside the repository in `~/.sextant-prod/secrets.env` after the user reset the scratch database password;
- updated `hosted_backup_restore_probe.py` so hosted Supabase restore proof dumps the application schema `public` plus required extensions `vector` and `pg_trgm`, rather than trying to recreate Supabase-managed platform schemas such as `auth`;
- ran the full backup/restore probe: production `pg_dump`, R2 upload to `s3://sextant-prod-wnam-objects/backups`, R2 download verification, scratch `psql` restore, and restored count validation.

Passed in the live working tree:

- initial TDD test failed because `pg_dump` did not include clean/schema/extension restore behavior, then `uv run pytest backend/tests/integration/test_hosted_backup_restore_probe.py -q` passed (`4 passed`);
- `uv run python -m compileall -q backend/scripts/hosted_backup_restore_probe.py` passed;
- `uv run python backend/scripts/hosted_backup_restore_probe.py --check-config` returned `hosted-backup-restore-config-ok`.

Passed against hosted production services:

- `uv run python backend/scripts/hosted_backup_restore_probe.py` returned `status=pass`;
- backup artifact ref was `s3://sextant-prod-wnam-objects/backups/hosted-readiness-backup-restore-20260701-f0c6ca51-2880-477d-b723-5757d3d31916.sql`;
- backup size was `614773` bytes with SHA-256 `c7c37b949517baa4d487c53252e2d0fbce479d9c274c6e1e85260fcac08fac52`;
- restored counts were `restored_source_deltas=5`, `restored_memory_pages=3`, and `restored_source_spans_with_raw=8`;
- source database host was `aws-1-us-west-1.pooler.supabase.com`, restore database host was `db.avjwnxdexbwdenipizfc.supabase.co`, and S3 endpoint host was `90e8f098f1c4dc0c6cfbbdd4f03c4248.r2.cloudflarestorage.com`;
- local production env now sets `SEXTANT_BACKUP_RESTORE_PROOF_REF=runbook://docs/progress-log/supabase-scratch-backup-restore-proof`;
- `bash scripts/validate-hosted-readiness.sh --allow-blocked` now reports only three missing values: `SEXTANT_INVITATION_DELIVERY_PROVIDER`, `SEXTANT_INVITATION_DELIVERY_PROOF_REF`, and `SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF`.

Observed results:

- the first full-database restore failed because Supabase scratch projects already include managed `auth` schema; the probe now restores the application schema and required application extensions only;
- the first application-schema restore failed on missing `public.vector`, and the next failed on missing `public.gin_trgm_ops`; adding `--extension vector --extension pg_trgm` to the logical dump fixed those application extension dependencies;
- backup/restore proof is no longer a hosted-readiness missing value. Invitation delivery and hosted observability proof remain intentionally unproven rather than filled with fake refs.

## Deployment Checkpoint - 2026-07-01 - VPS R2 Deploy, Observability Proof, And Vault Runtime Switch

Completed against hosted production services:

- direct SSH to `root@74.211.103.250` still timed out during banner exchange even after the VPS `sshd` service was active and listening, so the deployment used a private Cloudflare R2 handoff artifact instead of pretending SSH was fixed;
- uploaded backend source package `deploy-artifacts/sextant-backend-src-20260701T093044Z-402f07958b49.tar.gz` to private R2 bucket `sextant-prod-wnam-objects`, size `243245` bytes, SHA-256 `402f07958b49d1ea7d60dee5498c91dc60f6c708060fdf3670c30fd4aae6fb4b`;
- used KiwiVM root shell to download the R2 presigned artifact, verify SHA-256, back up `/opt/sextant/current/backend/src`, extract the updated backend source, compile key modules, and restart `sextant-api` and `sextant-worker`;
- verified `https://api.sextantlabs.net/health`, `/observability/traces`, and `/observability/alerts` returned HTTP `200` after deployment;
- generated a real API trace sample with a Supabase Auth JWT by calling `GET /api/projects/{project_id}/context-pack-readiness` against smoke project `fc5d58ab-80bd-4761-adef-3593cc98c756`, which returned HTTP `200`;
- switched `/etc/sextant/sextant.env` on the VPS to `SEXTANT_LLM_API_KEY_SECRET_REF=supabase-vault://...`, removed direct `OPENAI_API_KEY` / `SEXTANT_OPENAI_API_KEY` entries, and restarted API/worker;
- captured sanitized KiwiVM runtime evidence: `direct_openai_key_count=0`, `secret_ref_scheme=supabase-vault`, `secret_ref_fingerprint=24ced8b21aca...7496c01`, `api_active=active`, and `worker_active=active`.

Passed in the live working tree:

- initial TDD test failed because `hosted_observability_pipeline_probe.py` did not parse Prometheus label values containing route templates such as `path="/api/projects/{project_id}/context-pack-readiness"`;
- fixed the parser to extract metric names independently from label-block braces, then `uv run pytest backend/tests/integration/test_hosted_observability_pipeline_probe.py::test_hosted_observability_metrics_parser_accepts_route_template_labels -q` passed;
- `uv run pytest backend/tests/integration/test_hosted_observability_pipeline_probe.py -q` passed (`5 passed`).

Passed against hosted production services:

- `uv run python backend/scripts/hosted_observability_pipeline_probe.py` with `SEXTANT_HOSTED_METRICS_URL=https://api.sextantlabs.net/metrics`, `SEXTANT_HOSTED_TRACES_URL=https://api.sextantlabs.net/observability/traces`, `SEXTANT_ALERTING_DASHBOARD_URL=https://api.sextantlabs.net/observability/alerts`, `SEXTANT_OBSERVABILITY_REQUIRED_METRICS=sextant_api_requests_total`, `SEXTANT_OBSERVABILITY_TRACES_EXPECT=trace_sample_count`, and `SEXTANT_OBSERVABILITY_ALERTS_EXPECT=active_alert_count` returned `status=pass`;
- observability probe evidence hashes were metrics SHA-256 `86085b0258d70e7a9fdc4e7f40c43e446bd4e9c53617b377960cd22966a7f713`, traces SHA-256 `e98fbb246427ec3176520da35ee96f5408bb63068a25221791e6995102b865cf`, and alerts SHA-256 `bdc67e149160e9d3d20d11fb07dbdca3dbd83ad6f2c89f161bc661f5ca88d876`;
- local production env now sets `SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF=runbook://docs/progress-log/self-hosted-observability-pipeline-proof` plus the hosted metrics/traces/alerts URLs and expected markers;
- after the VPS runtime switched to Supabase Vault, `uv run python backend/scripts/hosted_external_smoke.py` with a freshly issued Supabase JWT returned `status=pass`, job `5675e86c-a009-40f1-a3f0-e8592c72dbdc`, `job_status=succeeded`, `evidence_log_count=1`, `fact_count=1`, `graph_edge_count=1`, `memory_page_count=1`, and `memory_answer_source_span_count=3`;
- `bash scripts/validate-hosted-readiness.sh --allow-blocked` now reports only two missing values: `SEXTANT_INVITATION_DELIVERY_PROVIDER` and `SEXTANT_INVITATION_DELIVERY_PROOF_REF`.
- final targeted verification after documentation updates passed: `uv run pytest backend/tests/integration/test_hosted_observability_pipeline_probe.py backend/tests/integration/test_production_config_gate.py::test_hosted_readiness_gate_records_external_blockers_without_faking_success -q` passed (`6 passed`), hosted observability probe returned `status=pass` with metrics series count `5`, hosted-readiness still reported only the two invitation delivery values above, and `git diff --check` plus trailing-whitespace scan passed for the changed docs/probe/test files.

Observed results:

- SSH remains a VPS access issue: TCP connects to `74.211.103.250:22`, but OpenSSH still times out during banner exchange and the VPS does not see those inbound sessions with `ss`; this no longer blocks the current deployment because the R2 + KiwiVM shell path worked, but it remains an operational access issue;
- observability is no longer a hosted-readiness missing value;
- VPS-side managed secret runtime is no longer using direct OpenAI environment keys according to sanitized shell evidence and post-switch hosted smoke;
- invitation delivery remains intentionally unconfigured and is the only hosted-readiness blocker.

## Completion Blocker Audit - 2026-07-01 - Invitation Delivery

Current hosted-readiness result:

- `set -a; source ~/.sextant-prod/secrets.env; set +a; bash scripts/validate-hosted-readiness.sh --allow-blocked` returns `hosted-readiness-blocked`;
- the only missing values are `SEXTANT_INVITATION_DELIVERY_PROVIDER` and `SEXTANT_INVITATION_DELIVERY_PROOF_REF`.

Source requirements checked:

- `implementation/08-api-contracts.md` requires `POST /projects/{project_id}/invitations` to record intent only and not send email or mint a token; hosted delivery execution and token issuance require external proof refs before they can count as complete;
- `implementation/12-observability-security-ops.md`, `implementation/13-acceptance-matrix.md`, `README.md`, and `docs/deployment-runbook.md` require real invitation delivery evidence from a production-shaped external provider/proof ref, without fake provider provisioning or fake invitation delivery;
- `scripts/validate-hosted-readiness.sh` currently accepts only `ses://`, `sendgrid://`, `postmark://`, `mailgun://`, or `smtp-tls://` invitation delivery providers.

External-platform check:

- Supabase Auth has an Admin invite capability that sends an invite link to an email address, and hosted Supabase email templates include an "Invite user" authentication email template;
- this is a possible existing-stack direction, but it is not currently an accepted `SEXTANT_INVITATION_DELIVERY_PROVIDER` scheme in the source/gate, and using it truthfully would still require an explicitly authorized recipient email, redirect URL/domain, and a real sent-invite artifact;
- the user previously deferred invitation delivery because the launch domain may change and there are no users, and asked to track it as production-ready TODO rather than add SES/SendGrid/Postmark/Mailgun/SMTP billing now.

Blocked conclusion:

- invitation delivery is the only remaining hosted-readiness blocker;
- it cannot be truthfully closed by local code, synthetic JSON, Supabase Auth capability claims, or ProjectInvitation intent/proof recording alone;
- next valid completion path requires either selecting/configuring a real delivery provider and sending/verifying an invitation, or explicitly changing the source acceptance scope for pre-user production readiness.

## Deployment Checkpoint - 2026-07-01 - Supabase Auth Invitation Delivery Proof

Completed against hosted production services:

- implemented `supabase-auth://` as a production-shaped invitation delivery provider/proof scheme for the hosted invitation probe, hosted session-provider probe, hosted-readiness gate, and ProjectInvitation API refs;
- sent a real Supabase Auth admin invite to the explicitly authorized recipient through `POST /auth/v1/invite`; the sanitized API result returned HTTP `200`, recipient hash `1b3164ad984be4c46898063b1e36834882f3b0b153c420e73f712d35fa02a7de`, `recipient_matched=true`, and `invited_at_present=true`;
- verified delivery through Chrome/Gmail search on the authorized Gmail account without opening the invite link or recording message content; Gmail search returned one matching result, and the row text hash was `d1bc948805ec6783403a78b44146cf91a885017879da895bd9a5c6172ee97ec5`;
- added sanitized hosted artifact `web/public/readiness/invitation-delivery.json` and deployed Vercel production deployment `https://sextant-fjjgtu3wl-frankqdwang1-9171s-projects.vercel.app`, aliased to `https://app.sextantlabs.net`;
- `curl -fsS https://app.sextantlabs.net/readiness/invitation-delivery.json | python -m json.tool` returned the deployed artifact with `status=sent`, `message_count=1`, and `provider=supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email`;
- local production env now sets `SEXTANT_INVITATION_DELIVERY_PROVIDER=supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email`, `SEXTANT_INVITATION_DELIVERY_PROOF_REF=supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email/20260701T100523Z`, and `SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL=https://app.sextantlabs.net/readiness/invitation-delivery.json`.

Passed in the live working tree:

- red tests first failed on unsupported `supabase-auth://` scheme in `hosted_invitation_delivery_probe.py`, `hosted_session_provider_probe.py`, `validate-hosted-readiness.sh`, and the ProjectInvitation API contract;
- after implementation, `uv run pytest backend/tests/integration/test_hosted_invitation_delivery_probe.py::test_invitation_delivery_accepts_supabase_auth_admin_invite_refs -q` passed;
- `uv run pytest backend/tests/integration/test_hosted_session_provider_probe.py::test_hosted_session_provider_accepts_supabase_auth_invitation_delivery_refs -q` passed;
- `uv run pytest backend/tests/integration/test_api_contracts.py::test_project_invitation_endpoint_accepts_supabase_auth_admin_invite_refs -q` passed;
- `uv run pytest backend/tests/integration/test_production_config_gate.py::test_hosted_readiness_gate_records_external_blockers_without_faking_success -q` passed;
- `pnpm --dir web lint` passed;
- `pnpm --dir web build` passed;
- `pnpm dlx vercel@50.28.0 build --prod --yes` built `.vercel/output`;
- `pnpm dlx vercel@50.28.0 deploy --prebuilt --prod --yes` completed and aliased `app.sextantlabs.net`;
- `uv run python backend/scripts/hosted_invitation_delivery_probe.py --check-config` returned `hosted-invitation-delivery-config-ok`;
- `uv run python backend/scripts/hosted_invitation_delivery_probe.py` returned `status=pass`, `provider_scheme=supabase-auth`, `proof_ref_scheme=supabase-auth`, `message_count=1`, artifact SHA-256 `973cac01b37723cdf89f9400aafd319fc88137a297058d62b27bf847e38110de`, and artifact host `app.sextantlabs.net`;
- `bash scripts/validate-hosted-readiness.sh --allow-blocked` returned `hosted-readiness-config-ok`.
- post-deploy clean-context UI acceptance through Chrome at `https://app.sextantlabs.net` passed without source inspection: Supabase Auth login loaded `Hosted smoke chapter` at `hosted-smoke+2`; Ask Memory returned an evidence-boundary answer with `未找到证据`, `置信度 0%`, `证据段落 0`, and no error; candidate generation completed with evidence sections and no direct memory write; selecting a candidate produced `hosted-smoke+3`, recorded a SourceDelta, and queued writeback; writeback reached `回写任务 · 完成`; the review gate showed evidence paragraph and review item actions; confirming both changed them to `已记录`; opening Memory Pages showed 3 memory pages, confirmed graph edges, SourceDelta-backed evidence refs, and `hosted-smoke+3` source evidence.

Observed results:

- invitation delivery is no longer a hosted-readiness missing value;
- Custom SMTP remains deferred in `TODOs.md` until the real launch domain, sender identity, and commercial onboarding plan are known;
- the proof remains deliberately hash-only and does not publish the recipient address, invite link, email subject, message body, Supabase service key, or Gmail content.

## Orderly Pause Checkpoint - 2026-07-01 - Post-Invite Verification

Completed before pausing:

- fixed `web/eslint.config.mjs` so `pnpm --dir web lint` ignores Vercel prebuilt output under `.vercel/output`; the failure was against generated bundled assets after `vercel build --prod`, not source code;
- fixed `pyproject.toml` pytest collection with `--import-mode=importlib` so unit and integration tests may keep distinct files with the same basename without import mismatch;
- refreshed the Supabase smoke JWT using the existing refresh token after `hosted_external_smoke.py` returned HTTP `401`; the new access token and rotated refresh token were written only to the local production env file and were not printed.

Verification completed:

- `uv run pytest backend/tests/integration/test_hosted_invitation_delivery_probe.py backend/tests/integration/test_hosted_session_provider_probe.py backend/tests/integration/test_production_config_gate.py backend/tests/integration/test_api_contracts.py -q` passed (`153 passed`, one existing `fastapi.testclient` deprecation warning);
- `uv run pytest -q` passed (`633 passed`, one existing `fastapi.testclient` deprecation warning);
- `pnpm --dir web lint` passed after ignoring `.vercel/output`;
- `pnpm --dir web typecheck` passed;
- `pnpm --dir web build` passed;
- `pnpm --dir web test` passed (`15 files`, `111 tests`);
- `pnpm --dir web test:e2e` first failed because `http://127.0.0.1:8011/docs` was already in use; rerunning with `SEXTANT_E2E_API_PORT=8111 SEXTANT_E2E_WEB_PORT=5910 pnpm --dir web test:e2e` passed (`6 passed`);
- `bash scripts/validate-production-config.sh` returned `production-config-ok`;
- `uv run python backend/scripts/hosted_invitation_delivery_probe.py` returned `status=pass`, `provider_scheme=supabase-auth`, `proof_ref_scheme=supabase-auth`, `message_count=1`, and artifact SHA-256 `973cac01b37723cdf89f9400aafd319fc88137a297058d62b27bf847e38110de`;
- `bash scripts/validate-hosted-readiness.sh --allow-blocked` returned `hosted-readiness-config-ok`;
- `uv run python backend/scripts/hosted_external_smoke.py` returned `status=pass`, job `5b9feeed-0d7f-4ca6-b5ca-306275446a29`, `job_status=succeeded`, `source_delta_id=50628fb2-c536-4944-8855-f81c8155ad99`, `memory_answer_type=canon`, `memory_answer_source_span_count=4`, `evidence_log_count=1`, `fact_count=1`, `memory_page_count=1`, and `graph_edge_count=1`;
- `git diff --check -- AGENTS.md PLAN.md README.md docs experience goals implementation web backend scripts TODOs.md pyproject.toml` passed.

Pause state:

- no browser automation remains active; Chrome tabs created for Gmail/app verification were finalized;
- hosted readiness is not blocked on invitation delivery anymore;
- the remaining known non-readiness operational gap is direct SSH access to the VPS; current deploy/ops path used KiwiVM plus private R2 handoff.

## Orderly Pause Checkpoint - 2026-07-02 - Core Verification And Hosted Smoke Refresh

Completed before pausing:

- resumed from the post-invite verification state and kept the active goal open; this checkpoint does not claim final completion;
- ran `bash scripts/verify-core.sh`; the first run stopped at `ruff check` on `backend/src/sextant/infra/memory_extraction_openai.py` and `backend/tests/integration/test_application_use_cases.py`;
- fixed the deterministic lint/type issues without changing the memory extraction contract: removed an unused dynamic relation alias, kept the runtime Pydantic discriminated-union alias with precise lint/type ignores, and made dynamic `create_model` field definitions visible to static checking;
- refreshed the Supabase smoke JWT after the first hosted external smoke returned HTTP `401`; the rotated access/refresh tokens were written only to `~/.sextant-prod/secrets.env` and were not printed.

Verification completed:

- `uv run --python /opt/homebrew/bin/python3 ruff format --check backend/src/sextant/infra/memory_extraction_openai.py` passed;
- `uv run --python /opt/homebrew/bin/python3 ruff check backend/src/sextant/infra/memory_extraction_openai.py` passed;
- `uv run ty check backend/src/sextant/infra/memory_extraction_openai.py --output-format concise` passed;
- `uv run --python /opt/homebrew/bin/python3 pytest -q backend/tests/integration/test_memory_extraction_provider.py` passed (`14 passed`);
- `uv run --python /opt/homebrew/bin/python3 pytest -q backend/tests/integration/test_memory_extraction_provider.py backend/tests/integration/test_application_use_cases.py` passed (`55 passed`);
- rerun `bash scripts/verify-core.sh` passed end-to-end: backend `633 passed` with the existing `fastapi.testclient` deprecation warning; alembic upgrade to head on a temporary SQLite database passed; `backend/scripts/production_smoke.py` returned `status=pass` with job `31be0b86-4921-40cf-b4b9-12e3cd9096f2`; semgrep, ruff, `ty`, tach, frontend lint/typecheck/build/unit tests, and Playwright all completed; web unit tests reported `15 passed` files and `111 passed` tests; Playwright reported `6 passed`;
- `set -a; . ~/.sextant-prod/secrets.env; set +a; bash scripts/validate-production-config.sh` returned `production-config-ok`;
- `set -a; . ~/.sextant-prod/secrets.env; set +a; bash scripts/validate-hosted-readiness.sh --allow-blocked` returned `hosted-readiness-config-ok`;
- after refreshing the smoke JWT, `uv run python backend/scripts/hosted_external_smoke.py` returned `status=pass`, deployment URL `https://api.sextantlabs.net`, job `1b7ac118-2cf9-4e4b-a0bd-004bda94c7f2`, `job_status=succeeded`, `source_delta_id=1be1af05-a1e6-439a-bb4c-2a6f6782947b`, `memory_answer_type=canon`, `memory_answer_source_span_count=5`, `evidence_log_count=1`, `fact_count=1`, `memory_page_count=1`, and `graph_edge_count=1`.

Pause state:

- core verification is currently green from this checkpoint;
- production config and hosted readiness are green when the local production secrets are sourced;
- the active goal remains open because this was an orderly pause checkpoint, not a final completion audit;
- next resume point: run a final source-coverage/acceptance audit against `implementation/13-acceptance-matrix.md`, clean up any stale status wording in `docs/known-gaps.md` if it conflicts with current evidence, and only then decide whether the goal can be marked complete.

## Source Coverage Refresh - 2026-07-02 - Current Markdown Inventory

This section refreshes the current coverage state after the hosted proof
checkpoints. It supersedes older `remaining=hosted proof remains external`
phrasing in the 2026-06-29 intake section where later checkpoints have closed
those proof items. It does not, by itself, mark the goal complete; completion
still requires the final acceptance-matrix and clean-context audit.

Inventory command:

```bash
rg --files -g '*.md' | sort
```

Current inventory count: 71 Markdown files.

Coverage classes used below:

- `entry/status`: source-order, progress, gap, decision, readiness, runbook,
  or TODO control document; must stay aligned with current evidence.
- `memory-core`: source/evidence/memory/review/graph obligations covered by
  `B1+B2+B3+B5+B7` and the 2026-07-02 verification checkpoint.
- `agent-control`: agent, context-pack, candidate, storytelling-control, and
  prose-rendering obligations covered by `B4+B5+B6+B8` and hosted provider
  proof checkpoints.
- `experience`: user-facing writing/candidate/writeback/review/conversation
  obligations covered by `B1+B2+B4+B5` plus Playwright and hosted UI evidence.
- `implementation`: engineering specifications covered by the relevant `B1-B8`
  bundle, `scripts/verify-core.sh`, production config/readiness gates, and
  hosted probes.
- `prompt-skill`: prompt contract files covered by `B6`, prompt registry
  contract tests, golden drift tests, provider validation, and live provider
  eval proof.

Per-file current coverage:

- `AGENTS.md`: status=`covered-current`; class=`entry/status`; obligations=source-order execution, dirty-tree protection, source coverage, doc upkeep, clean-context acceptance discipline; unfinished=final completion audit still pending; evidence=this refresh, 2026-07-02 core verification, hosted readiness and smoke checkpoints.
- `AGENT_GOAL.md`: status=`covered-current`; class=`agent-control`; obligations=memory-backed writing copilot, author control, candidate/review loop; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B5+B6+B8`, hosted provider/live UI evidence.
- `GOAL.md`: status=`covered-current`; class=`memory-core`; obligations=evidence-backed memory, canon/review gates, retrieval, graph, author-sovereign writeback; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B3+B5+B7`, hosted smoke/readiness evidence.
- `PLAN.md`: status=`covered-current`; class=`entry/status`; obligations=complete source coverage, production implementation, no scope collapse, external proof discipline; unfinished=final acceptance-matrix audit still pending; evidence=this refresh, 2026-07-02 core verification, hosted readiness and smoke checkpoints.
- `PRODUCT.md`: status=`covered-current`; class=`entry/status`; obligations=quiet author-sovereign product direction and non-demo visual posture; unfinished=no file-specific blocker identified in this refresh; evidence=`B5`, deployed clean-context UI evidence.
- `README.md`: status=`covered-current`; class=`entry/status`; obligations=repo map, verification commands, hosted/runbook contract, non-fake completion boundaries; unfinished=keep current as final audit updates evidence; evidence=2026-07-02 README status correction and verification command results.
- `TODOs.md`: status=`active-follow-up`; class=`entry/status`; obligations=track production-readiness follow-ups without treating them as completion evidence; unfinished=direct VPS SSH, Custom SMTP, and possible future backend rollback drill remain operational follow-ups; evidence=current `TODOs.md`, `docs/known-gaps.md`.
- `docs/deployment-runbook.md`: status=`covered-current`; class=`entry/status`; obligations=production deployment interface, hosted probes, rollback/restore evidence contract; unfinished=runbook itself is not proof and must cite current probe/progress evidence; evidence=2026-07-02 runbook status correction, `B7`.
- `docs/goal-readiness-review.md`: status=`covered-current`; class=`entry/status`; obligations=truthful readiness judgment without overstating completion; unfinished=final completion audit pending; evidence=2026-07-02 readiness review correction.
- `docs/implementation-decisions.md`: status=`covered-current`; class=`entry/status`; obligations=record conflicts, scope, architecture, dependencies, persistence, security, and testing decisions; unfinished=append only when future decisions change scope truth; evidence=current decisions through dynamic OpenAI memory schema boundary.
- `docs/known-gaps.md`: status=`covered-current`; class=`entry/status`; obligations=record only real residual gaps or exact blockers; unfinished=direct VPS SSH and Custom SMTP are follow-ups, not current hosted-readiness blockers; evidence=2026-07-02 gaps wording correction and hosted-readiness gate.
- `docs/progress-log.md`: status=`covered-current`; class=`entry/status`; obligations=source coverage, checkpoint evidence, non-completion truth; unfinished=final completion audit pending; evidence=this section and 2026-07-02 verification checkpoint.
- `docs/superpowers/plans/2026-06-29-target-documentation-cleanup.md`: status=`covered-current`; class=`entry/status`; obligations=remove invalid prose-regex semantic direction and distinguish infrastructure from completed SkillRegistry/runtime work; unfinished=no file-specific blocker identified in this refresh; evidence=`B6+B8`, docs correction checkpoints.
- `docs/superpowers/specs/2026-06-29-source-pipeline-cleanup-design.md`: status=`covered-current`; class=`entry/status`; obligations=delete local prose semantic parsing and route creative semantics through skills/providers plus validators; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B6+B8`, source-pipeline cleanup tests.
- `experience/README.md`: status=`covered-current`; class=`experience`; obligations=bind writing, candidate, writeback, review, and conversation contracts; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B4+B5`.
- `experience/00-product-principles.md`: status=`covered-current`; class=`experience`; obligations=author sovereignty, evidence traceability, non-demo behavior; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B5`.
- `experience/01-writing-session-loop.md`: status=`covered-current`; class=`experience`; obligations=session loop from source/draft through acceptance and visible writeback consequences; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B4+B5`, Playwright and hosted UI evidence.
- `experience/02-action-request-contract.md`: status=`covered-current`; class=`experience`; obligations=typed ActionRequest creation, execution, status, audit; unfinished=no file-specific blocker identified in this refresh; evidence=`B2+B4`, API contract and action-request tests.
- `experience/03-candidate-lifecycle.md`: status=`covered-current`; class=`experience`; obligations=candidate states, author actions, overrides, accepted-fragment backwrite; unfinished=no file-specific blocker identified in this refresh; evidence=`B2+B4+B5`.
- `experience/04-memory-writeback-contract.md`: status=`covered-current`; class=`experience`; obligations=preview, review, canon gate, evidence-backed writeback; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B5`, hosted smoke.
- `experience/05-review-and-risk-contract.md`: status=`covered-current`; class=`experience`; obligations=review types, dispute/risk handling, non-canon risk surfacing; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B4+B5`.
- `experience/06-conversational-entry-contract.md`: status=`covered-current`; class=`experience`; obligations=evidence/context-backed conversational memory answers; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B4+B5`, hosted smoke memory answer evidence.
- `goals/00-design-principles.md`: status=`covered-current`; class=`memory-core`; obligations=evidence-first architecture, author control, deterministic policy boundaries; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B5`.
- `goals/01-data-flow.md`: status=`covered-current`; class=`memory-core`; obligations=source-to-memory-to-candidate round trip; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B4+B5+B7`.
- `goals/02-core-data-structures.md`: status=`covered-current`; class=`memory-core`; obligations=domain entities for source, evidence, memory, review, graph, and agent surfaces; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B4`, migrations/schema tests.
- `goals/03-source-evidence.md`: status=`covered-current`; class=`memory-core`; obligations=SourceDelta, SourceSpan, EvidenceLogEntry, ancestry, no evidence bypass; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B7`, hosted smoke.
- `goals/04-scenes-pov.md`: status=`covered-current`; class=`agent-control`; obligations=scene modeling, POV constraints, provider-boundary adjudication without local prose heuristics; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B6+B8`, hosted provider live eval.
- `goals/05-mentions-aliases.md`: status=`covered-current`; class=`memory-core`; obligations=mention extraction, alias resolution, ambiguity review; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B8`.
- `goals/06-entities-events-facts.md`: status=`covered-current`; class=`memory-core`; obligations=entity/event/fact modeling, evidence-backed derivation, conflict handling; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B6+B7`.
- `goals/07-memory-pages.md`: status=`covered-current`; class=`memory-core`; obligations=memory page materialization, rewrite workflow, canon/proposed separation; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B5`.
- `goals/08-graph-projection.md`: status=`covered-current`; class=`memory-core`; obligations=rebuildable graph edges that never become fact authority; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B5`.
- `goals/09-retrieval-context-pack.md`: status=`covered-current`; class=`memory-core`; obligations=context-pack retrieval, readiness, retrieval-backed memory answers; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B8`, hosted pgvector recall proof.
- `goals/10-continuity-check.md`: status=`covered-current`; class=`memory-core`; obligations=continuity answer surface with evidence, caveats, unknowns; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B5`.
- `goals/11-non-goals.md`: status=`covered-current`; class=`memory-core`; obligations=avoid chat-first takeover, non-evidenced canon writes, graph-as-truth shortcuts; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B4+B5`.
- `goals/12-inspirations.md`: status=`covered-current`; class=`entry/status`; obligations=preserve intended product shape without broad redesign or chat collapse; unfinished=no file-specific blocker identified in this refresh; evidence=`PRODUCT.md`, `B5`.
- `goals/13-skills-and-resolver.md`: status=`covered-current`; class=`agent-control`; obligations=Story Skills, SkillRegistry, Resolver, metadata/runtime, deterministic validator boundary; unfinished=no file-specific blocker identified in this refresh; evidence=`B6+B8`, hosted provider live eval.
- `goals/14-story-schema-packs.md`: status=`covered-current`; class=`agent-control`; obligations=project/story schema pack storage, API, validation, replayable edits; unfinished=no file-specific blocker identified in this refresh; evidence=`B2+B4+B5`.
- `goals/15-event-aggregation.md`: status=`covered-current`; class=`agent-control`; obligations=provider-boundary event aggregation with deterministic adjudication outcomes; unfinished=no file-specific blocker identified in this refresh; evidence=`B6+B8`, hosted provider live eval.
- `goals/16-source-normalization.md`: status=`covered-current`; class=`memory-core`; obligations=normalized source views and source-version handling before downstream derivation; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B7`.
- `goals/17-incremental-memory-writeback.md`: status=`covered-current`; class=`memory-core`; obligations=incremental writeback, preview, idempotency, review/canon gating; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B7`.
- `goals/18-conflict-policy.md`: status=`covered-current`; class=`memory-core`; obligations=dispute policy, overrides, blocked canon promotion flows; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2`.
- `goals/19-story-auto-link.md`: status=`covered-current`; class=`memory-core`; obligations=SourceDelta search/indexing and auto-link support; unfinished=no file-specific blocker identified in this refresh; evidence=`B7`, hosted reindex proof.
- `goals/20-agent-overview.md`: status=`covered-current`; class=`agent-control`; obligations=agent proposal loop downstream of memory/context and upstream of author acceptance; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B5+B8`.
- `goals/21-writing-context-pack.md`: status=`covered-current`; class=`agent-control`; obligations=WritingContextPack with memory, graph, review-aware context; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B8`.
- `goals/22-character-agency-profile.md`: status=`covered-current`; class=`agent-control`; obligations=character agency/risk signals feed candidate review without direct canon writes; unfinished=no file-specific blocker identified in this refresh; evidence=`B4`.
- `goals/23-next-page-agent.md`: status=`covered-current`; class=`agent-control`; obligations=next-page drafting through provider/story-skill boundary into author-reviewable candidates; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B6+B8`, hosted provider live eval.
- `goals/24-draft-candidate-lifecycle.md`: status=`covered-current`; class=`agent-control`; obligations=candidate states, acceptance/rejection/override, accepted-fragment backwrite; unfinished=no file-specific blocker identified in this refresh; evidence=`B2+B4+B5`.
- `goals/25-agent-memory-writeback.md`: status=`covered-current`; class=`agent-control`; obligations=accepted agent output re-enters evidence/writeback path; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B4+B7`.
- `goals/26-agent-review-policy.md`: status=`covered-current`; class=`agent-control`; obligations=AgentReviewFinding distinct from ReviewItem and routed through formal review operations; unfinished=no file-specific blocker identified in this refresh; evidence=`B2+B4+B5`.
- `goals/27-storytelling-control-layer.md`: status=`covered-current`; class=`agent-control`; obligations=control objects constrain generation without memory/canon authority; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B6+B8`.
- `goals/28-role-need-and-cast-expansion.md`: status=`covered-current`; class=`agent-control`; obligations=role-need and cast-expansion structures feed candidate generation with policy constraints; unfinished=no file-specific blocker identified in this refresh; evidence=`B4`.
- `goals/29-new-character-policy.md`: status=`covered-current`; class=`agent-control`; obligations=new-character seeds and policy gating before durable adoption; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B5`.
- `goals/30-dramatization-layer.md`: status=`covered-current`; class=`agent-control`; obligations=dramatization controls stay in generation/review space, not canon space; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B6`.
- `goals/31-inner-state-rendering.md`: status=`covered-current`; class=`agent-control`; obligations=inner-state rendering constraints and review-safe prose generation; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B6`, hosted provider live eval.
- `goals/32-scene-sequel-mode.md`: status=`covered-current`; class=`agent-control`; obligations=scene/sequel constraints flow through story schema and candidate generation; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B6`.
- `goals/33-prose-rendering-contract.md`: status=`covered-current`; class=`agent-control`; obligations=prose rendering contract shapes provider output and candidate review without memory/canon authority; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B6+B8`.
- `implementation/README.md`: status=`covered-current`; class=`implementation`; obligations=map engineering specs to implementation surfaces; unfinished=no file-specific blocker identified in this refresh; evidence=`B1-B8`.
- `implementation/00-overview.md`: status=`covered-current`; class=`implementation`; obligations=overall production architecture, non-demo behavior, hosted proof discipline; unfinished=final completion audit pending; evidence=`B1-B8`, 2026-07-02 core verification.
- `implementation/01-source-of-truth-map.md`: status=`covered-current`; class=`implementation`; obligations=map source documents to concrete code areas; unfinished=no file-specific blocker identified in this refresh; evidence=this coverage refresh, `B1+B2+B4+B5`.
- `implementation/02-module-boundaries.md`: status=`covered-current`; class=`implementation`; obligations=domain/application/api/infra/skills boundaries and guardrails; unfinished=no file-specific blocker identified in this refresh; evidence=`tach check`, `B1+B2+B4+B6`.
- `implementation/03-persistence-schema.md`: status=`covered-current`; class=`implementation`; obligations=relational schema, migrations, constraints, idempotency, lifecycle persistence; unfinished=no file-specific blocker identified in this refresh; evidence=alembic upgrade in `verify-core`, hosted Postgres/backup proof.
- `implementation/04-domain-state-machines.md`: status=`covered-current`; class=`implementation`; obligations=explicit lifecycle transitions and invalid-transition failures; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B4`, domain state tests.
- `implementation/05-application-use-cases.md`: status=`covered-current`; class=`implementation`; obligations=typed use cases for source ingest, writeback, review, conversation, candidate operations; unfinished=no file-specific blocker identified in this refresh; evidence=`B1+B2+B4`.
- `implementation/06-story-skills-and-llm-harness.md`: status=`covered-current`; class=`implementation`; obligations=Story Skills, resolver, runtime, replay/eval contracts, provider boundary; unfinished=no file-specific blocker identified in this refresh; evidence=`B6+B8`, hosted provider live eval.
- `implementation/07-agent-and-storytelling-control.md`: status=`covered-current`; class=`implementation`; obligations=agent/story control structures, candidate policies, control surfaces; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B5+B6+B8`.
- `implementation/08-api-contracts.md`: status=`covered-current`; class=`implementation`; obligations=typed schemas, idempotent writes, deterministic errors, generated client sync; unfinished=no file-specific blocker identified in this refresh; evidence=`B2`, generated API artifacts tests.
- `implementation/09-frontend-integration.md`: status=`covered-current`; class=`implementation`; obligations=API-backed workbench behavior without broad redesign; unfinished=no file-specific blocker identified in this refresh; evidence=`B5`, deployed clean-context UI evidence.
- `implementation/10-worker-and-jobs.md`: status=`covered-current`; class=`implementation`; obligations=worker catalog, job handlers, retries, health, pipeline execution; unfinished=no file-specific blocker identified in this refresh; evidence=`B3+B7`, hosted worker capacity proof.
- `implementation/11-ci-cd-and-ai-guardrails.md`: status=`covered-current`; class=`implementation`; obligations=CI/security/guardrails, replay tests, anti-fake completion controls; unfinished=no file-specific blocker identified in this refresh; evidence=`scripts/verify-core.sh`, `.github/workflows/*`, semgrep/security tests.
- `implementation/12-observability-security-ops.md`: status=`covered-current`; class=`implementation`; obligations=observability, redaction, hosted secrets/session/object-store/post-deploy ops evidence; unfinished=direct SSH remains ops follow-up, not hosted-readiness blocker; evidence=`B3+B7`, hosted observability/secret/session/object-store/backup proofs.
- `implementation/13-acceptance-matrix.md`: status=`covered-current`; class=`implementation`; obligations=all acceptance rows pass or have exact blockers; unfinished=no file-specific blocker identified in this refresh; evidence=2026-07-02 acceptance matrix audit, core verification, hosted smoke, hosted-readiness evidence, hosted backend source redeploy proof, and hosted clean-context UI acceptance.
- `implementation/14-implementation-pr-stack.md`: status=`covered-current`; class=`implementation`; obligations=delivery ordering and dependency sequencing; unfinished=no file-specific blocker identified in this refresh; evidence=current repo surface across `B1-B8`.
- `prompts/skills/openai_event_aggregation/openai-event-aggregation.v1.md`: status=`covered-current`; class=`prompt-skill`; obligations=structured event-adjudication prompt with no canon authority and evidence requirement; unfinished=no file-specific blocker identified in this refresh; evidence=`B6`, provider/golden/live eval tests.
- `prompts/skills/openai_memory_extraction/openai-memory-extraction.v1.md`: status=`covered-current`; class=`prompt-skill`; obligations=structured memory/thread candidate extraction with no direct memory/canon authority; unfinished=no file-specific blocker identified in this refresh; evidence=`B6`, provider/golden/live eval tests.
- `prompts/skills/openai_pov_detection/openai-pov-detection.v1.md`: status=`covered-current`; class=`prompt-skill`; obligations=structured POV detection from provided mentions only; unfinished=no file-specific blocker identified in this refresh; evidence=`B6`, provider/golden/live eval tests.
- `prompts/skills/openai_story_draft/openai-story-draft.v1.md`: status=`covered-current`; class=`prompt-skill`; obligations=story-draft generation under POV/risk constraints and no canon authority; unfinished=no file-specific blocker identified in this refresh; evidence=`B4+B6`, provider/golden/live eval tests.
- `web/README.md`: status=`covered-current`; class=`implementation`; obligations=frontend setup, API-mode runtime, test commands, hosted auth configuration, workbench behavior expectations; unfinished=no file-specific blocker identified in this refresh; evidence=`B5`, 2026-07-02 frontend verification via `verify-core`.

## Acceptance Matrix Audit - 2026-07-02 - Evidence Inputs And Remaining Completion Checks

Audit inputs inspected in this checkpoint:

- `implementation/13-acceptance-matrix.md`;
- current backend test inventory under `backend/tests`;
- current hosted probe scripts under `backend/scripts/hosted_*`;
- current release gates in `scripts/verify-core.sh`,
  `scripts/validate-production-config.sh`, and
  `scripts/validate-hosted-readiness.sh`;
- current frontend tests under `web/tests` and `web/e2e`;
- current CI/security surfaces under `.github/workflows` and `.semgrep`;
- fresh 2026-07-02 verification evidence from `scripts/verify-core.sh`,
  production config/readiness gates, and hosted external smoke.

Current matrix evidence:

- Core flow: ActionRequest, candidate lifecycle, stale-base protection,
  SourceDelta/SourceSpan, memory writeback, review lifecycle, graph projection,
  MemoryPage operations, and project story schema requirements have direct
  backend/API/frontend tests in `test_action_request_run.py`,
  `test_agent_candidate_job.py`, `test_agent_review_job.py`,
  `test_api_contracts.py`, `test_application_use_cases.py`,
  `test_memory_writeback.py`, `test_memory_answer_context_pack.py`,
  `test_persistence_schema.py`, `test_source_delta_reindex.py`, and the
  workbench unit/e2e suites.
- Documentation and skill architecture correction: target docs, runtime
  surfaces, real-corpus eval, prompt registry, golden drift, and provider
  validation are covered by `test_story_skill_runtime.py`,
  `test_real_corpus_skill_eval.py`, `test_provider_golden.py`,
  `test_prompt_registry.py`, and the source coverage refresh above.
- Agent acceptance: WritingContextPack, risk/canon separation, storytelling
  controls, prose rendering contract, target range risk, new-character policy,
  POV/inner-state constraints, scene/sequel modes, and control-risk handling
  are covered by `test_memory_answer_context_pack.py`,
  `test_agent_candidate_job.py`, `test_agent_review_job.py`,
  `test_prose_contract_review.py`, and `test_story_schema.py`.
- Persistence acceptance: Alembic empty-database upgrade, lifecycle enum/check
  constraints, SourceSpan range validation, current processed-view uniqueness,
  idempotency, and canon-promotion gate behavior are covered by
  `test_migrations.py`, `test_persistence_schema.py`,
  `test_domain_state_machines.py`, and `verify-core`'s Alembic upgrade step.
- API acceptance: generated OpenAPI/client drift and documented route coverage
  are covered by `test_generated_api_artifacts.py`; idempotency and deterministic
  error mapping are covered by `test_api_contracts.py` and
  `test_application_use_cases.py`; route-layer boundaries are covered by
  `tach check`.
- Frontend acceptance: selected-text ActionRequest, candidate accept with base
  hash/range, partial accept, high-risk override paths, ReviewItem vs
  AgentReviewFinding separation, MemoryPage/GraphProjection panels, project
  schema, project membership, and invitation intent/proof refs are covered by
  `web/tests/*` and `web/e2e/workbench.spec.ts`.
- CI acceptance: `verify-core` runs formatting, ruff, `ty`, `tach`, full
  backend tests, Alembic upgrade, semgrep, production smoke, hosted-readiness
  shape validation, frontend lint/typecheck/build/unit tests, and Playwright.
  `test_semgrep_rules.py` proves the direct-canon, graph-to-fact, and
  provider-to-memory guardrails catch fixtures. Hosted proof-ref and artifact URL
  secret-bearing negative paths are covered by hosted probe tests and
  `test_production_config_gate.py`.
- Production smoke acceptance: local `production_smoke.py` passed inside
  `verify-core`; hosted external smoke passed against
  `https://api.sextantlabs.net` with job
  `1b7ac118-2cf9-4e4b-a0bd-004bda94c7f2`, SourceDelta-backed writeback,
  canon memory answer, MemoryPage, and GraphProjection evidence.

Remaining completion checks before any goal-complete claim:

- no source-document acceptance blocker was identified in this checkpoint after
  the hosted backend source redeploy and hosted clean-context UI acceptance;
- the final verification command set must still be re-run after these status
  document edits, and any failure must be fixed or recorded as an exact blocker
  before a goal-complete claim.

Additional verification after status-document edits:

- `git diff --check -- README.md docs/deployment-runbook.md docs/goal-readiness-review.md docs/known-gaps.md docs/progress-log.md` passed;
- stale-current-status search for old hosted-blocker phrases across
  `README.md`, `docs/goal-readiness-review.md`, `docs/known-gaps.md`,
  `docs/deployment-runbook.md`, and `docs/progress-log.md` returned no matches
  for the targeted obsolete phrases;
- `set -a; . ~/.sextant-prod/secrets.env; set +a; bash scripts/validate-production-config.sh` returned `production-config-ok`;
- `set -a; . ~/.sextant-prod/secrets.env; set +a; bash scripts/validate-hosted-readiness.sh --allow-blocked` returned `hosted-readiness-config-ok`;
- `set -a; . ~/.sextant-prod/secrets.env; set +a; bash scripts/validate-hosted-readiness.sh` returned `hosted-readiness-config-ok`.

## Hosted Backend Source Redeploy - 2026-07-02

Scope:

- reconciled the hosted VPS backend source with the current local runtime source
  after local static-check/runtime source edits;
- preserved the existing VPS deployment shape and did not record or commit any
  secret-bearing presigned URL.

Artifact and deployment evidence:

- private R2 artifact
  `deploy-artifacts/sextant-backend-src-20260702T014256Z-4f45a5f7d2b6.tar.gz`
  was uploaded with SHA-256
  `4f45a5f7d2b6efca431eae2a67264ca7ab3ee9e2ead42c85b91b9c6783364438`
  and size `242717` bytes;
- initial KiwiVM heredoc/`pipefail` attempts were rejected or only replayed the
  task text, so they were not treated as deployment evidence;
- production deploy was re-run through KiwiVM advanced shell as a single
  `base64 -> /tmp script -> bash` command; KiwiVM returned `Completed`;
- the deployment script internally failed closed on artifact SHA mismatch,
  source compile failure, expected runtime-source SHA mismatch, inactive
  `sextant-api`/`sextant-worker`, or failed production health;
- a second safe remote verification script, without secret-bearing URLs,
  checked `/opt/sextant/current/backend/.last-src-deploy`, compileall, expected
  SHA-256 values for the four runtime files changed since the previous deploy,
  systemd active state, and production health; KiwiVM returned `Completed`.

Expected hosted runtime source SHA-256 values verified by the safe remote script:

- `backend/src/sextant/application/use_cases.py`:
  `021370bc851f2ff9ed0523eb5b36080dbe0c928393a9b705d74ea783293da814`;
- `backend/src/sextant/common/observability.py`:
  `1f85390e4ac40363d3f092b48abc49deddcad15966a146e6814fb437fa0c667b`;
- `backend/src/sextant/infra/memory_extraction_openai.py`:
  `0d739054e07e04f26e118ccd852fe085d74fa1e3bf3248a0986b2b1dd09acdb6`;
- `backend/src/sextant/infra/source_pipeline.py`:
  `ec59397a2bb85714082c940caa7b6a7b84fc22936773dcc9ac486fc75874e67c`.

Post-deploy hosted verification:

- `curl -fsS --max-time 15 https://api.sextantlabs.net/health` returned
  `status=ok`, `service=sextant-api`, `release_environment=production`, and
  `deployment_version=2026.07.01+vps.74.211.103.250`;
- `set -a; . ~/.sextant-prod/secrets.env; set +a; uv run python backend/scripts/hosted_external_smoke.py`
  returned `status=pass` against `https://api.sextantlabs.net`, job
  `955ceb4a-43c2-4869-8fa8-4157bfd12e0b`, SourceDelta
  `c10f73a9-c6a1-47bc-a0c3-fbc7cc56748c`, canon memory answer,
  `memory_answer_source_span_count=7`, `evidence_log_count=1`,
  `fact_count=1`, `memory_page_count=1`, and `graph_edge_count=1`;
- `set -a; . ~/.sextant-prod/secrets.env; set +a; bash scripts/validate-hosted-readiness.sh`
  returned `hosted-readiness-config-ok`.

Remaining after this checkpoint:

- hosted backend source/deployment alignment is closed for this checkpoint;
- hosted clean-context UI acceptance is recorded in the next checkpoint;
- the final verification command set must be re-run after status-document edits.

## Hosted Clean-Context UI Acceptance - 2026-07-02

Surface:

- browser-only acceptance against `https://app.sextantlabs.net`;
- authenticated with the production smoke user through the visible Supabase Auth
  login form;
- no source code or local docs were used as a substitute for UI evidence during
  the walkthrough.

Observed pass evidence:

- login page showed `登录生产工作台`, email/password fields, and production API
  target `https://api.sextantlabs.net`;
- successful login loaded `Hosted smoke chapter`, version `hosted-smoke+3`,
  current scene card, `0 个待处理`, and context sections for known/unknown facts,
  risk, pressure points, graph-like object/location and character motivation
  projections;
- opening the candidate/review drawer before processing showed a pending
  continuity warning with evidence source, default policy action, review
  controls, and no direct canon write path;
- submitting the visible review gate changed the drawer to `0 个待处理` and
  showed `thread update accepted`, Memory Page update, SourceSpan IDs,
  SourceDelta IDs, EvidenceLog IDs, and context-rewrite marking;
- Ask Sextant negative memory query returned `未找到证据`, confidence `0%`,
  `证据段落 0`, and `POV 不可直接用`, proving the UI did not fabricate memory when
  evidence was absent;
- Ask Sextant positive memory query `what was on the paper?` returned
  `可用记忆`, confidence `95%`, `证据段落 1`, `POV 可用`, and associated entities
  including `She`, `seeing_faded_ink_on_paper`, and `faded_ink_paper`;
- project panel showed version fingerprints, membership, invitation-intent
  controls, story-rule counts, material inventory, and SourceDelta/job status
  history from the hosted API;
- `改写这一段 1` triggered hosted candidate generation and displayed
  `正在生成候选，不会写入正文或记忆`; after completion it showed sentence-level
  candidates, `只采纳这一句`, disabled save/apply controls before selection,
  evidence paragraphs, and risk explanation.

Acceptance judgment:

- pass for the required browser/computer-use hosted UI acceptance gate;
- no UI-only fake-success state was observed in this walkthrough;
- the Memory Page top-bar badge still displayed `—` even after writeback, but
  the review result, memory answer, project panel, SourceDelta list, context card,
  and hosted smoke all exposed SourceSpan/EvidenceLog/MemoryPage/graph evidence,
  so this is not recorded as a completion blocker.

## Final Verification Checkpoint - 2026-07-02

Commands:

- `git diff --check -- AGENTS.md PLAN.md README.md docs experience goals implementation web backend scripts .github .semgrep pyproject.toml tach.toml`
  passed;
- `bash scripts/verify-core.sh` passed:
  - backend format/lint/type/module-boundary checks passed;
  - backend test suite passed with `633 passed, 1 warning`;
  - Alembic empty-database upgrade completed through
    `af1b2c3d4e5f`;
  - semgrep/security checks ran inside the core gate;
  - local production smoke returned `status=pass`;
  - frontend `eslint`, `tsc`, `vite build`, Vitest, and Playwright ran;
  - frontend Vitest passed `111` tests;
  - Playwright passed `6` e2e tests;
- `set -a; . ~/.sextant-prod/secrets.env; set +a; bash scripts/validate-production-config.sh`
  returned `production-config-ok`;
- `set -a; . ~/.sextant-prod/secrets.env; set +a; bash scripts/validate-hosted-readiness.sh`
  returned `hosted-readiness-config-ok`;
- `set -a; . ~/.sextant-prod/secrets.env; set +a; uv run python backend/scripts/hosted_external_smoke.py`
  returned `status=pass` against `https://api.sextantlabs.net`, job
  `1a431bb0-351c-4165-b94a-bb7d9d4d3af4`, SourceDelta
  `281bcfcf-b029-4679-9c88-5d1fb4ee3fd8`, canon memory answer,
  `memory_answer_source_span_count=8`, `evidence_log_count=1`,
  `fact_count=1`, `memory_page_count=1`, and `graph_edge_count=1`;
- `lsof -nP -iTCP:8121 -sTCP:LISTEN || true` and
  `lsof -nP -iTCP:5821 -sTCP:LISTEN || true` returned no listeners after the
  verification run.

Current completion assessment:

- all current source Markdown obligations identified in the 2026-07-02 source
  coverage refresh are implemented or covered by recorded hosted evidence;
- `implementation/13-acceptance-matrix.md` is satisfied for this checkpoint by
  the automated core gate, strict hosted-readiness gate, hosted backend source
  redeploy, hosted external smoke, and hosted browser-only UI acceptance;
- direct VPS SSH access and Custom SMTP remain production-readiness follow-ups in
  `TODOs.md`, not current source-document completion blockers;
- no known blocker is being carried forward from this checkpoint.
