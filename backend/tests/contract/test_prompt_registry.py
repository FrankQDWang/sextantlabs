from __future__ import annotations

import json
from pathlib import Path

from sextant.infra.prompt_registry import REQUIRED_PROMPT_METADATA, load_prompt

REPO_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_OPENAI_PROMPTS = (
    ("openai_story_draft", "openai-story-draft.v1"),
    ("openai_pov_detection", "openai-pov-detection.v1"),
    ("openai_memory_extraction", "openai-memory-extraction.v1"),
    ("openai_event_aggregation", "openai-event-aggregation.v1"),
)


def test_required_openai_prompts_have_complete_metadata() -> None:
    for skill_name, prompt_version in REQUIRED_OPENAI_PROMPTS:
        prompt = load_prompt(skill_name, prompt_version)

        assert prompt.skill_name == skill_name
        assert prompt.prompt_version == prompt_version
        assert prompt.body.strip()
        for field_name in REQUIRED_PROMPT_METADATA:
            assert prompt.metadata.get(field_name)
        assert prompt.model_constraints.get("structured_output") is True
        assert prompt.golden_cases
        assert prompt.failure_cases


def test_prompt_lock_hashes_match_versioned_prompt_files() -> None:
    for skill_name, prompt_version in REQUIRED_OPENAI_PROMPTS:
        prompt = load_prompt(skill_name, prompt_version)
        expected_path = (
            REPO_ROOT / "evals" / "expected" / "prompts" / f"{prompt_version}.expected.json"
        )
        expected = json.loads(expected_path.read_text(encoding="utf-8"))

        assert expected["skill_name"] == skill_name
        assert expected["prompt_version"] == prompt_version
        assert expected["prompt_hash"] == prompt.content_hash
        assert expected["golden_cases"] == prompt.golden_cases
        assert expected["failure_cases"] == prompt.failure_cases
