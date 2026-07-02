from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ALLOWED_PROOF_SCHEMES = {"runbook", "https", "ci-artifact"}
ALLOWED_REVIEWER_MODES = {"browser-computer-use", "browser-only", "computer-use"}
REQUIRED_CHECKS = (
    "project_source",
    "source_normalization",
    "selected_text",
    "candidate_request",
    "evidence_risk_avoided_claims",
    "partial_acceptance",
    "source_delta_span_evidence",
    "memory_writeback",
    "review_queue",
    "persistence_reload",
    "placeholder_check",
)


class ConfigError(RuntimeError):
    pass


class CleanContextAcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class CleanContextAcceptanceConfig:
    deployment_url: str
    deployment_url_host: str
    deployment_version: str
    raw_proof_ref: str
    proof_ref_scheme: str
    artifact_url: str
    artifact_url_host: str
    bearer_token: str | None
    timeout_seconds: float
    expected_statuses: tuple[str, ...]
    min_steps: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> CleanContextAcceptanceConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "clean-context UI acceptance proof."
            )
        deployment_url = _required(env, "SEXTANT_DEPLOYMENT_URL")
        deployment_url_host = _validate_hosted_https_url("SEXTANT_DEPLOYMENT_URL", deployment_url)
        deployment_version = _required(env, "SEXTANT_DEPLOYMENT_VERSION")
        raw_proof_ref = _required(env, "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF")
        proof_ref_scheme = _validate_proof_ref(raw_proof_ref)
        artifact_url = _artifact_url(env, raw_proof_ref, proof_ref_scheme)
        artifact_url_host = _validate_hosted_https_url(
            "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_ARTIFACT_URL", artifact_url
        )
        return cls(
            deployment_url=deployment_url,
            deployment_url_host=deployment_url_host,
            deployment_version=deployment_version,
            raw_proof_ref=raw_proof_ref,
            proof_ref_scheme=proof_ref_scheme,
            artifact_url=artifact_url,
            artifact_url_host=artifact_url_host,
            bearer_token=_optional(env, "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_BEARER_TOKEN"),
            timeout_seconds=_positive_float(
                env.get("SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_TIMEOUT_SECONDS", "10"),
                "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_TIMEOUT_SECONDS",
            ),
            expected_statuses=_expected_statuses(
                env.get(
                    "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_EXPECT_STATUSES", "pass,passed,success"
                )
            ),
            min_steps=_positive_int(
                env.get("SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_MIN_STEPS", "8"),
                "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_MIN_STEPS",
            ),
        )


ArtifactFetcher = Callable[[CleanContextAcceptanceConfig], dict[str, object]]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe hosted Sextant clean-context UI acceptance evidence."
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help=(
            "Validate hosted clean-context acceptance probe configuration without network requests."
        ),
    )
    args = parser.parse_args()
    try:
        config = CleanContextAcceptanceConfig.from_env(dict(os.environ))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if args.check_config:
        print("hosted-clean-context-acceptance-config-ok")
        return
    try:
        result = run_clean_context_acceptance_probe(config)
    except (CleanContextAcceptanceError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def run_clean_context_acceptance_probe(
    config: CleanContextAcceptanceConfig,
    *,
    artifact_fetcher: ArtifactFetcher | None = None,
) -> dict[str, object]:
    fetcher = artifact_fetcher or fetch_acceptance_artifact
    report = fetcher(config)
    deployment_url = _field_text(report, "deployment_url")
    if deployment_url.rstrip("/") != config.deployment_url.rstrip("/"):
        raise CleanContextAcceptanceError(
            "Clean-context acceptance artifact reported deployment URL "
            f"{deployment_url!r}; expected {config.deployment_url!r}."
        )
    deployment_version = _field_text(report, "deployment_version")
    if deployment_version != config.deployment_version:
        raise CleanContextAcceptanceError(
            "Clean-context acceptance artifact reported deployment version "
            f"{deployment_version!r}; expected {config.deployment_version!r}."
        )
    acceptance_status = _field_text(report, "status").lower()
    if acceptance_status not in config.expected_statuses:
        raise CleanContextAcceptanceError(
            "Clean-context acceptance artifact has not passed: "
            f"{acceptance_status!r} not in {config.expected_statuses!r}."
        )
    reviewer_mode = _field_text(report, "reviewer_mode").lower()
    if reviewer_mode not in ALLOWED_REVIEWER_MODES:
        raise CleanContextAcceptanceError(
            "Clean-context acceptance must be browser/computer-use only; "
            f"got reviewer_mode={reviewer_mode!r}."
        )
    if not _field_bool(report, "used_final_built_app_ui"):
        raise CleanContextAcceptanceError(
            "Clean-context acceptance artifact must confirm use of the final built app UI."
        )
    if _field_bool(report, "source_inspection") or _field_bool(report, "docs_inspection"):
        raise CleanContextAcceptanceError(
            "Clean-context acceptance artifact reports source/docs inspection."
        )
    failure_count = _failure_count(report)
    if failure_count:
        raise CleanContextAcceptanceError(
            f"Clean-context acceptance artifact contains {failure_count} failure entries."
        )
    required_check_count = _validate_required_checks(report)
    step_count = _step_count(report, config.min_steps)
    return {
        "status": "pass",
        "deployment_url_host": config.deployment_url_host,
        "deployment_version": deployment_version,
        "acceptance_status": acceptance_status,
        "reviewer_mode": reviewer_mode,
        "step_count": step_count,
        "required_check_count": required_check_count,
        "artifact_url_host": config.artifact_url_host,
        "artifact_url_path_sha256": _sha256(urlparse(config.artifact_url).path or "/"),
        "artifact_sha256": _artifact_hash(report),
        "proof_ref_scheme": config.proof_ref_scheme,
        "proof_ref_sha256": _sha256(config.raw_proof_ref),
    }


def fetch_acceptance_artifact(config: CleanContextAcceptanceConfig) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if config.bearer_token is not None:
        headers["Authorization"] = f"Bearer {config.bearer_token}"
    request = Request(config.artifact_url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Clean-context acceptance probe failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("Clean-context acceptance probe could not reach artifact URL.") from exc
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Clean-context acceptance artifact did not return JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Clean-context acceptance artifact must be a JSON object.")
    return payload


def _artifact_url(env: Mapping[str, str], raw_proof_ref: str, proof_ref_scheme: str) -> str:
    configured = env.get("SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_ARTIFACT_URL", "").strip()
    if proof_ref_scheme == "https":
        return configured or raw_proof_ref
    if not configured:
        raise ConfigError(
            "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_ARTIFACT_URL is required when "
            "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF is not an HTTPS artifact URL."
        )
    return configured


def _validate_proof_ref(value: str) -> str:
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_PROOF_SCHEMES or not (parsed.netloc or parsed.path.lstrip("/")):
        raise ConfigError(
            "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF must be an auditable "
            "runbook://, https://, or ci-artifact:// reference."
        )
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ConfigError(
            "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF must not include URL "
            "userinfo, params, query strings, or fragments."
        )
    if scheme == "https":
        _validate_hosted_https_url("SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF", value)
    return scheme


def _field_text(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise CleanContextAcceptanceError(
            f"Clean-context acceptance artifact field {field_name!r} must be text."
        )
    return value.strip()


def _field_bool(payload: Mapping[str, object], field_name: str) -> bool:
    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise CleanContextAcceptanceError(
            f"Clean-context acceptance artifact field {field_name!r} must be boolean."
        )
    return value


def _failure_count(payload: Mapping[str, object]) -> int:
    failures = payload.get("failures", [])
    if not isinstance(failures, list):
        raise CleanContextAcceptanceError(
            "Clean-context acceptance artifact field 'failures' must be a list."
        )
    return len(failures)


def _validate_required_checks(payload: Mapping[str, object]) -> int:
    checks = payload.get("required_checks")
    if not isinstance(checks, Mapping):
        raise CleanContextAcceptanceError(
            "Clean-context acceptance artifact field 'required_checks' must be an object."
        )
    missing_or_false = [name for name in REQUIRED_CHECKS if checks.get(name) is not True]
    if missing_or_false:
        raise CleanContextAcceptanceError(
            "Clean-context acceptance artifact missing required passed checks: "
            + ", ".join(missing_or_false)
        )
    return len(REQUIRED_CHECKS)


def _step_count(payload: Mapping[str, object], min_steps: int) -> int:
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise CleanContextAcceptanceError(
            "Clean-context acceptance artifact field 'steps' must be a list."
        )
    step_count = len([step for step in steps if isinstance(step, str) and step.strip()])
    if step_count < min_steps:
        raise CleanContextAcceptanceError(
            "Clean-context acceptance artifact has "
            f"{step_count} walkthrough steps; expected at least {min_steps}."
        )
    return step_count


def _expected_statuses(value: str) -> tuple[str, ...]:
    statuses = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    if not statuses:
        raise ConfigError("SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_EXPECT_STATUSES must not be empty.")
    return statuses


def _validate_hosted_https_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if parsed.scheme != "https" or not host:
        raise ConfigError(f"{name} must be a hosted HTTPS URL.")
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ConfigError(
            f"{name} must not include URL userinfo, params, query strings, or fragments."
        )
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local host.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local address.")
    return host


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required for hosted clean-context UI acceptance proof.")
    return value


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _positive_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive number.") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive number.")
    return parsed


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive integer.")
    return parsed


def _artifact_hash(payload: Mapping[str, object]) -> str:
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
