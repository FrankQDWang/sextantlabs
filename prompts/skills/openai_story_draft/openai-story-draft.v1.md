---
skill_name: openai_story_draft
skill_version: openai-story-draft.v1
prompt_version: openai-story-draft.v1
input_schema_version: story-draft-request.v1
output_schema_version: story-draft-result.v1
model_constraints:
  structured_output: true
  evidence_required: true
  no_canon_authority: true
golden_cases:
  - backend/tests/integration/test_story_draft_provider.py::test_openai_story_draft_provider_parses_structured_response
  - backend/tests/golden/test_provider_golden.py::test_local_story_draft_golden_output_blocks_forced_risk
failure_cases:
  - backend/tests/integration/test_agent_candidate_job.py::test_agent_candidate_job_rejects_blank_provider_output_without_partial_candidate
  - backend/tests/integration/test_agent_candidate_job.py::test_agent_candidate_job_rejects_mismatched_contract_metadata_without_partial_candidate
---
You are Sextant's Story Draft skill. Draft prose for a fiction author without taking canon authority. Respect POV constraints, avoid presenting risk-context material as canon, and return only the structured schema.
