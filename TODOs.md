# Production-Ready TODOs

This file tracks production-readiness work that is intentionally not being treated
as complete yet. Items here may be acceptable for the current single-author
smoke deployment, but they remain blockers for final production acceptance only
when the source documents make them acceptance gates.

## Current Stack Boundary

Use the existing paid/free stack first:

- Supabase for database, auth, pgvector, and, if feasible, secret storage.
- Vercel for the hosted web app, deployment history, domain aliases, and rollback
  drill evidence.
- Cloudflare for DNS, R2 object storage, and R2 access-policy evidence.
- The VPS for the always-on API, worker, self-hosted operational endpoints, and
  deployment runbooks.

Do not add AWS Secrets Manager, GCP Secret Manager, Vault, Grafana Cloud,
SendGrid, Postmark, Mailgun, SES, or another paid managed service unless the
user explicitly approves it later.

## Production Readiness Items

- Custom SMTP: defer Supabase Custom SMTP setup until the real launch domain,
  sender identity, and commercial onboarding plan are known. Current
  hosted-readiness uses a real Supabase Auth admin invite through the existing
  stack; do not add SES/SendGrid/Postmark/Mailgun/SMTP billing without explicit
  later approval.
- VPS access: direct SSH to `74.211.103.250:22` remains unhealthy because the
  client times out during SSH banner exchange even though the VPS sshd service
  is active. Current deployment used KiwiVM shell plus private R2 artifact
  handoff. Restore direct SSH or document KiwiVM/R2 as the operational runbook
  before final ops handoff.
- Rollback drill: Vercel alias rollback drill was executed and restored on
  2026-07-01, and proof refs are aligned to `docs/progress-log.md`. Remaining
  work is only any later backend/VPS rollback drill if the source documents
  require service-side rollback beyond the web alias drill.

## Closed Evidence Items

- Secret management: Supabase Vault support is implemented and verified against
  the production Supabase project. The VPS runtime env now has no direct
  `OPENAI_API_KEY` / `SEXTANT_OPENAI_API_KEY` entries, uses a
  `supabase-vault://` secret ref, and post-switch hosted external smoke passed.
- Observability: the VPS API now serves `/metrics`, `/observability/traces`,
  and `/observability/alerts`; a real API request generated trace evidence, and
  `hosted_observability_pipeline_probe.py` passed against the hosted endpoints.
- R2 IAM proof: Cloudflare R2 bucket `sextant-prod-wnam-objects` and token
  `sextant-prod-r2-runtime-wnam` evidence are published as a sanitized readiness
  artifact at `https://app.sextantlabs.net/readiness/object-store-iam.json`.
  `hosted_object_store_iam_probe.py` passed with `cloudflare-r2://` proof ref,
  and hosted readiness no longer reports `SEXTANT_OBJECT_STORE_IAM_PROOF_REF`
  as missing.
- Session-provider proof: Supabase Auth provisioning and token-issuer artifacts
  are deployed under `https://app.sextantlabs.net/readiness/` and probes pass.
- Invitation delivery: Supabase Auth admin invite was sent to the explicitly
  authorized recipient, verified through Chrome/Gmail search without reading the
  invite link, and published as a sanitized hosted artifact at
  `https://app.sextantlabs.net/readiness/invitation-delivery.json`.
  `hosted_invitation_delivery_probe.py` passed with `supabase-auth://` refs, and
  hosted readiness no longer reports invitation delivery missing.
- Proof-ref alignment for already-passed hosted checks: deployment, R2
  read/write, worker capacity, provider live eval, pgvector recall, external
  smoke, clean-context UI acceptance, SourceDelta search reindex, and Vercel
  rollback refs are aligned to auditable `docs/progress-log.md` evidence.
- Backup/restore proof: Supabase scratch project
  `avjwnxdexbwdenipizfc` restored the production `public` schema plus required
  `vector` and `pg_trgm` extensions from an R2 backup artifact. The hosted
  backup/restore probe passed and hosted readiness no longer reports
  `SEXTANT_BACKUP_RESTORE_PROOF_REF` as missing.

## Non-Completion Rule

These TODOs are not placeholders for success. A TODO can be closed only by code,
configuration, runbook evidence, and verification output that satisfy the
source-of-truth documents and `implementation/13-acceptance-matrix.md`.
