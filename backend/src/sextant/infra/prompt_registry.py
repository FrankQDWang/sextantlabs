from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

REQUIRED_PROMPT_METADATA = (
    "skill_name",
    "skill_version",
    "prompt_version",
    "input_schema_version",
    "output_schema_version",
    "model_constraints",
    "golden_cases",
    "failure_cases",
)


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    path: Path
    metadata: dict[str, object]
    body: str

    @property
    def skill_name(self) -> str:
        return str(self.metadata["skill_name"])

    @property
    def skill_version(self) -> str:
        return str(self.metadata["skill_version"])

    @property
    def prompt_version(self) -> str:
        return str(self.metadata["prompt_version"])

    @property
    def input_schema_version(self) -> str:
        return str(self.metadata["input_schema_version"])

    @property
    def output_schema_version(self) -> str:
        return str(self.metadata["output_schema_version"])

    @property
    def model_constraints(self) -> dict[str, object]:
        return cast(dict[str, object], self.metadata["model_constraints"])

    @property
    def golden_cases(self) -> list[str]:
        return cast(list[str], self.metadata["golden_cases"])

    @property
    def failure_cases(self) -> list[str]:
        return cast(list[str], self.metadata["failure_cases"])

    @property
    def content_hash(self) -> str:
        payload = (
            f"path:{self.path.relative_to(_repo_root())}\n"
            f"metadata:{_stable_metadata(self.metadata)}\n"
            f"body:{self.body.strip()}\n"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_prompt(skill_name: str, prompt_version: str) -> PromptDefinition:
    path = _prompt_root() / "skills" / skill_name / f"{prompt_version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    prompt = _parse_prompt_file(path)
    if prompt.skill_name != skill_name:
        raise ValueError("Prompt skill_name metadata does not match path.")
    if prompt.prompt_version != prompt_version:
        raise ValueError("Prompt prompt_version metadata does not match path.")
    return prompt


def _prompt_root() -> Path:
    configured = os.environ.get("SEXTANT_PROMPT_ROOT")
    if configured:
        return Path(configured)
    return _repo_root() / "prompts"


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "AGENTS.md").exists() and (parent / "PLAN.md").exists():
            return parent
    raise RuntimeError("Could not locate Sextant repository root.")


def _parse_prompt_file(path: Path) -> PromptDefinition:
    raw = path.read_text(encoding="utf-8")
    metadata, body = _split_front_matter(raw)
    _validate_metadata(metadata, path)
    if not body.strip():
        raise ValueError(f"Prompt body is empty: {path}")
    return PromptDefinition(path=path, metadata=metadata, body=body.strip())


def _split_front_matter(raw: str) -> tuple[dict[str, object], str]:
    if not raw.startswith("---\n"):
        raise ValueError("Prompt file requires YAML-style front matter.")
    parts = raw.split("---\n", maxsplit=2)
    if len(parts) != 3:
        raise ValueError("Prompt file front matter is not closed.")
    return _parse_simple_yaml(parts[1]), parts[2]


def _parse_simple_yaml(raw: str) -> dict[str, object]:
    metadata: dict[str, object] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - "):
            if current_key is None or not isinstance(metadata.get(current_key), list):
                raise ValueError("Prompt list item has no list parent.")
            cast(list[str], metadata[current_key]).append(line.removeprefix("  - ").strip())
            continue
        if line.startswith("  "):
            if current_key is None or not isinstance(metadata.get(current_key), dict):
                raise ValueError("Prompt nested key has no mapping parent.")
            key, value = _split_key_value(line.strip())
            cast(dict[str, object], metadata[current_key])[key] = _parse_scalar(value)
            continue

        key, value = _split_key_value(line)
        if value:
            metadata[key] = _parse_scalar(value)
            current_key = key
            continue
        if key in {"model_constraints"}:
            metadata[key] = {}
        else:
            metadata[key] = []
        current_key = key
    return metadata


def _split_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError(f"Prompt metadata line is not key/value: {line}")
    key, value = line.split(":", maxsplit=1)
    key = key.strip()
    if not key:
        raise ValueError("Prompt metadata key is empty.")
    return key, value.strip()


def _parse_scalar(value: str) -> object:
    if value == "true":
        return True
    if value == "false":
        return False
    return value.strip('"')


def _validate_metadata(metadata: dict[str, object], path: Path) -> None:
    missing = [field for field in REQUIRED_PROMPT_METADATA if not metadata.get(field)]
    if missing:
        raise ValueError(f"Prompt metadata missing {', '.join(missing)}: {path}")
    if not isinstance(metadata["model_constraints"], dict):
        raise ValueError(f"Prompt model_constraints must be a mapping: {path}")
    if not isinstance(metadata["golden_cases"], list):
        raise ValueError(f"Prompt golden_cases must be a list: {path}")
    if not isinstance(metadata["failure_cases"], list):
        raise ValueError(f"Prompt failure_cases must be a list: {path}")


def _stable_metadata(metadata: dict[str, object]) -> str:
    lines: list[str] = []
    for key in sorted(metadata):
        value = metadata[key]
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for nested_key in sorted(value):
                lines.append(f"  {nested_key}: {value[nested_key]}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)
