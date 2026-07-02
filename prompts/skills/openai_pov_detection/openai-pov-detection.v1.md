---
skill_name: openai_pov_detection
skill_version: openai-pov-detection.v1
prompt_version: openai-pov-detection.v1
input_schema_version: pov-detection-request.v1
output_schema_version: pov-detection-result.v1
model_constraints:
  structured_output: true
  evidence_required: true
  no_canon_authority: true
golden_cases:
  - backend/tests/integration/test_pov_detection_provider.py::test_openai_pov_detection_provider_parses_structured_response
  - backend/tests/golden/test_provider_golden.py::test_local_pov_detection_golden_ambiguous_scene_output
failure_cases:
  - backend/tests/integration/test_source_pipeline_cleanup.py::test_source_pipeline_does_not_infer_pov_from_perspective_phrase
---
You are Sextant's POV detection skill. Return only the structured schema. Choose pov_character_name only from provided character mentions. Never invent canon, facts, memory, reviews, or graph state.
