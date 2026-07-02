# Known Gaps

## Current Gaps Correction - 2026-07-01

Hosted proof refs now validate through the readiness gate. The local thin-harness + rich-skills architecture gap is also closed in the working tree.

## Active Gaps

- direct SSH access to the VPS remains operationally unhealthy: TCP connects to `74.211.103.250:22`, but OpenSSH times out during banner exchange and the VPS did not observe those inbound sessions. Current deployment used KiwiVM shell plus private R2 artifact handoff instead of SSH, so this is an access/runbook gap rather than a current hosted-readiness blocker.
- Custom SMTP remains deferred until the real launch domain, sender identity, and commercial onboarding plan are known; current hosted readiness uses Supabase Auth admin invite evidence instead of adding a paid mail provider.
- `TODOs.md` now tracks production-ready TODOs that are intentionally not completion evidence. Secret management, self-hosted observability, R2 IAM, session/token proof, invitation delivery, rollback alias drill, and Supabase scratch backup/restore proof have been moved to closed evidence after hosted validation.

## Hosted Evidence Reverified On 2026-07-01

Live verification evidence:

- `bash scripts/validate-production-config.sh` failed only on missing production configuration, not on code/runtime errors;
- `bash scripts/validate-hosted-readiness.sh --allow-blocked` now returns `hosted-readiness-config-ok`.
- `uv run python backend/scripts/hosted_external_smoke.py` later returned `status=pass` against `https://api.sextantlabs.net`;
- `SEXTANT_HOSTED_WORKER_METRICS_URL=https://api.sextantlabs.net/worker-metrics uv run python backend/scripts/hosted_worker_capacity_probe.py` returned `status=pass`;
- `uv run python backend/scripts/hosted_provider_live_eval_probe.py` returned `status=pass` for all five provider skills;
- `SEXTANT_PGVECTOR_RECALL_PROJECT_ID=fc5d58ab-80bd-4761-adef-3593cc98c756 uv run python backend/scripts/hosted_pgvector_recall_probe.py` returned `status=pass`.
- Vercel deployment `dpl_4QoHJ1SQWJwnJmFciuH7BCNmgcsJ` was created for the new `sextant-web` project and aliased as `https://sextant-web-nine.vercel.app`;
- browser-based hosted UI acceptance at `https://sextant-web-nine.vercel.app` passed runtime Supabase login, memory page viewing, evidence-boundary memory Q&A, candidate acceptance, and memory writeback completion after the relation-role schema fix;
- Supabase Postgres confirmed the latest hosted UI writeback job `7fac172d-a503-4fc2-a61e-a82edc6c7247` succeeded and SourceDelta `0238c2af-1e36-4d4d-bc59-e90c6dff1176` reached `memory_writeback_completed`.
- `uv run python backend/scripts/hosted_source_delta_reindex_probe.py --batch-size 20 --all` returned `status=pass`, `rebuild_all=true`, and `reindexed_rows=5` against Supabase/R2 after fixing full-rebuild cursor pagination.
- `app.sextantlabs.net` was added to Vercel project `sextant-web`, verified by Vercel as `configured_correctly`, aliased to the production deployment, and loaded in Chrome with runtime Supabase login plus API-backed memory pages.
- `uv run python backend/scripts/hosted_object_store_iam_probe.py` returned `status=pass` against the hosted Cloudflare R2 artifact at `https://app.sextantlabs.net/readiness/object-store-iam.json`; hosted readiness no longer reports `SEXTANT_OBJECT_STORE_IAM_PROOF_REF` as missing.
- self-hosted observability endpoint code is now deployed to the VPS API: `https://api.sextantlabs.net/metrics`, `/observability/traces`, and `/observability/alerts` returned HTTP `200`, and `uv run python backend/scripts/hosted_observability_pipeline_probe.py` returned `status=pass`;
- `uv run python backend/scripts/hosted_backup_restore_probe.py` returned `status=pass` after restoring production `public` schema plus `vector` and `pg_trgm` extensions into Supabase scratch project `avjwnxdexbwdenipizfc`; hosted readiness no longer reports `SEXTANT_BACKUP_RESTORE_PROOF_REF` as missing.
- the VPS runtime was switched to Supabase Vault for provider credentials: sanitized KiwiVM evidence recorded `direct_openai_key_count=0`, `secret_ref_scheme=supabase-vault`, API/worker services active, and a post-switch hosted external smoke returned `status=pass`;
- `uv run python backend/scripts/hosted_invitation_delivery_probe.py` returned `status=pass` against the hosted Supabase Auth invite artifact, after the admin invite was sent and Gmail delivery was verified through Chrome.

Current exact hosted evidence groups:

- proof-ref alignment for completed live evidence: deployment, object-store read/write, worker capacity, provider live eval, pgvector recall, external smoke, clean-context UI acceptance, SourceDelta search reindex, and Vercel rollback proof refs are now set in the local production env as `runbook://docs/progress-log/...` refs. They still depend on keeping `docs/progress-log.md` current and auditable;
- object-store IAM proof update: `SEXTANT_OBJECT_STORE_IAM_PROOF_REF=cloudflare-r2://sextant-prod-wnam-objects/runtime-token` is now set in the local production env, the hosted artifact is deployed under `app.sextantlabs.net`, and the probe passed without exposing token secrets, account ids, or raw policy documents;
- managed secret-manager proof: Supabase Vault support is implemented and verified against production Supabase with `supabase-vault://ientixxmbdeoqdmkublx/sextant_openai_api_key`; `hosted_secret_manager_probe.py` passed, hosted provider live eval passed with direct OpenAI env keys unset, and the VPS runtime now reports no direct OpenAI env keys plus a Supabase Vault secret-ref scheme;
- session/token proof update: Supabase Auth provisioning and token-issuer artifacts are now hosted at `https://app.sextantlabs.net/readiness/session-provider-provisioning.json` and `https://app.sextantlabs.net/readiness/token-issuer.json`; both corresponding probes returned `status=pass`, and the local production env now has `supabase://ientixxmbdeoqdmkublx/auth` proof refs;
- invitation delivery proof: Supabase Auth admin invite evidence is hosted at `https://app.sextantlabs.net/readiness/invitation-delivery.json`; the local production env now has `supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email` provider/proof refs and the hosted invitation probe passed;
- observability proof: self-hosted traces and alert-state endpoints are implemented and deployed, and `SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF` now points to progress-log evidence after the hosted probe passed against real metrics/traces/alerts endpoints;
- DR proof update: `SEXTANT_BACKUP_RESTORE_PROOF_REF` now points to `runbook://docs/progress-log/supabase-scratch-backup-restore-proof` after a real Supabase scratch restore validated SourceDelta, MemoryPage, and SourceSpan -> RawSource counts. A real Vercel alias rollback drill was executed and restored on 2026-07-01, and rollback proof refs are aligned to `docs/progress-log.md` evidence rather than a synthetic placeholder.

The 2026-07-01 implementation pass added first-class `StorySkillRegistry`, `run_skill(...)`, Resolver planning, real-corpus Fanren boundary eval assets, Codex judge rubric metadata, RRF retrieval fusion, and sliding-window context organization. These close the local architecture gaps but do not reduce the need to keep hosted proof evidence auditable.

## Useful Existing Infrastructure

- source import/versioning and SourceDelta/SourceSpan/EvidenceLogEntry mechanics;
- persistence, API, worker, review, memory, graph, auth, object-store, observability, and frontend integration implementations;
- provider ports/adapters, prompt files, prompt hash locks, `SkillRun` persistence, replay-diff evaluation, provider-boundary guardrails, explicit scene metadata handling, and structured `FACT:` / `THREAD:` local directive parsing.

## Guardrails That Still Apply

- Prompt registry alone is not SkillRegistry; current completion evidence depends on the separate StorySkillRegistry, resolver, runtime, and validation surfaces.
- Provider adapters alone are not Story Skill architecture; current completion evidence depends on the story-skill runtime, replay/eval harness, provider validation, and application wiring.
- Local deterministic providers are still not semantic quality proof; provider/live-eval proof must remain tied to production provider configuration and sanitized hosted evidence.
- Local green tests are still not hosted readiness; hosted readiness is proved only by the production config/readiness gates plus hosted probes recorded in `docs/progress-log.md`.
- Browser-only local walkthroughs are still not deployed acceptance; clean-context acceptance must remain tied to the hosted UI/browser evidence recorded in `docs/progress-log.md`.
