from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

NOOP_EXECUTABLES = {"cat", "date", "echo", "false", "ls", "printf", "pwd", "sleep", "true"}


class ConfigError(RuntimeError):
    pass


class RollbackDrillError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class RollbackDrillConfig:
    status_url: str
    status_url_host: str
    bearer_token: str | None
    current_version: str
    target_version: str
    command_args: tuple[str, ...]
    command_text: str
    raw_runbook_ref: str
    runbook_ref_scheme: str
    timeout_seconds: float
    poll_attempts: int
    poll_interval_seconds: float
    version_field: str
    health_field: str
    expected_health: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> RollbackDrillConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "rollback drill proof."
            )
        status_url = _required(env, "SEXTANT_ROLLBACK_STATUS_URL")
        status_url_host = _validate_hosted_https_url("SEXTANT_ROLLBACK_STATUS_URL", status_url)
        current_version = _required(env, "SEXTANT_DEPLOYMENT_VERSION")
        target_version = _required(env, "SEXTANT_ROLLBACK_TARGET_VERSION")
        if target_version == current_version:
            raise ConfigError("rollback target version must differ from current version.")
        command_text = _required(env, "SEXTANT_ROLLBACK_COMMAND")
        command_args = _parse_rollback_command(command_text, target_version)
        raw_runbook_ref = _required(env, "SEXTANT_ROLLBACK_RUNBOOK_REF")
        runbook_ref_scheme = _validate_runbook_ref(raw_runbook_ref)
        return cls(
            status_url=status_url,
            status_url_host=status_url_host,
            bearer_token=_optional(env, "SEXTANT_ROLLBACK_STATUS_BEARER_TOKEN"),
            current_version=current_version,
            target_version=target_version,
            command_args=command_args,
            command_text=command_text,
            raw_runbook_ref=raw_runbook_ref,
            runbook_ref_scheme=runbook_ref_scheme,
            timeout_seconds=_positive_float(
                env.get("SEXTANT_ROLLBACK_TIMEOUT_SECONDS", "300"),
                "SEXTANT_ROLLBACK_TIMEOUT_SECONDS",
            ),
            poll_attempts=_positive_int(
                env.get("SEXTANT_ROLLBACK_POLL_ATTEMPTS", "30"),
                "SEXTANT_ROLLBACK_POLL_ATTEMPTS",
            ),
            poll_interval_seconds=_positive_float(
                env.get("SEXTANT_ROLLBACK_POLL_INTERVAL_SECONDS", "2"),
                "SEXTANT_ROLLBACK_POLL_INTERVAL_SECONDS",
            ),
            version_field=env.get("SEXTANT_ROLLBACK_STATUS_VERSION_FIELD", "version").strip()
            or "version",
            health_field=env.get("SEXTANT_ROLLBACK_STATUS_HEALTH_FIELD", "status").strip()
            or "status",
            expected_health=env.get("SEXTANT_ROLLBACK_STATUS_EXPECT_HEALTH", "ok").strip() or "ok",
        )


StatusFetcher = Callable[[RollbackDrillConfig], dict[str, object]]
CommandRunner = Callable[[tuple[str, ...]], CommandResult]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a hosted Sextant rollback drill through deployment tooling."
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted rollback drill configuration without network or rollback execution.",
    )
    args = parser.parse_args()
    try:
        config = RollbackDrillConfig.from_env(dict(os.environ))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if args.check_config:
        print("hosted-rollback-drill-config-ok")
        return
    try:
        result = run_rollback_drill_probe(config)
    except (RollbackDrillError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def run_rollback_drill_probe(
    config: RollbackDrillConfig,
    *,
    status_fetcher: StatusFetcher | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    fetcher = status_fetcher or fetch_status
    runner = command_runner or _subprocess_runner(config)

    pre_status = fetcher(config)
    pre_version = _field_text(pre_status, config.version_field)
    if pre_version != config.current_version:
        raise RollbackDrillError(
            "Hosted rollback drill pre-check saw version "
            f"{pre_version!r}; expected current deployment version "
            f"{config.current_version!r}."
        )

    command_result = runner(config.command_args)
    if command_result.returncode != 0:
        raise RollbackDrillError(
            f"Hosted rollback command failed with exit code {command_result.returncode}."
        )

    latest_status = pre_status
    latest_version = pre_version
    latest_health = _field_text(pre_status, config.health_field)
    polls_used = 0
    for poll_number in range(1, config.poll_attempts + 1):
        latest_status = fetcher(config)
        latest_version = _field_text(latest_status, config.version_field)
        latest_health = _field_text(latest_status, config.health_field)
        polls_used = poll_number
        if latest_version == config.target_version and latest_health == config.expected_health:
            break
        if poll_number < config.poll_attempts:
            time.sleep(config.poll_interval_seconds)
    else:
        raise RollbackDrillError(
            "Hosted rollback drill did not observe target rollback version "
            f"{config.target_version!r} with health {config.expected_health!r}."
        )

    return {
        "status": "pass",
        "status_url_host": config.status_url_host,
        "status_url_path_sha256": _sha256(urlparse(config.status_url).path or "/"),
        "pre_rollback_version": pre_version,
        "post_rollback_version": latest_version,
        "post_rollback_health": latest_health,
        "expected_health": config.expected_health,
        "poll_attempts": polls_used,
        "command_exit_code": command_result.returncode,
        "command_sha256": _sha256(config.command_text),
        "command_stdout_sha256": _sha256(command_result.stdout),
        "command_stderr_sha256": _sha256(command_result.stderr),
        "pre_status_sha256": _status_hash(pre_status),
        "post_status_sha256": _status_hash(latest_status),
        "runbook_ref_scheme": config.runbook_ref_scheme,
        "runbook_ref_sha256": _sha256(config.raw_runbook_ref),
    }


def fetch_status(config: RollbackDrillConfig) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if config.bearer_token is not None:
        headers["Authorization"] = f"Bearer {config.bearer_token}"
    request = Request(config.status_url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Rollback status probe failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("Rollback status probe could not reach hosted status URL.") from exc
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Rollback status URL did not return JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Rollback status URL must return a JSON object.")
    return payload


def _subprocess_runner(config: RollbackDrillConfig) -> CommandRunner:
    def run(args: tuple[str, ...]) -> CommandResult:
        completed = subprocess.run(
            args,
            capture_output=True,
            check=False,
            timeout=config.timeout_seconds,
            text=True,
        )
        return CommandResult(
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            returncode=completed.returncode,
        )

    return run


def _field_text(payload: Mapping[str, object], field_path: str) -> str:
    value: object = payload
    for part in field_path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise RollbackDrillError(f"Rollback status field {field_path!r} is missing.")
        value = value[part]
    if not isinstance(value, str) or not value.strip():
        raise RollbackDrillError(f"Rollback status field {field_path!r} must be text.")
    return value.strip()


def _parse_rollback_command(command_text: str, target_version: str) -> tuple[str, ...]:
    try:
        parts = tuple(shlex.split(command_text))
    except ValueError as exc:
        raise ConfigError("SEXTANT_ROLLBACK_COMMAND must be shell-parseable.") from exc
    if not parts:
        raise ConfigError("SEXTANT_ROLLBACK_COMMAND is required for rollback drill.")
    executable = os.path.basename(parts[0]).lower()
    if executable in NOOP_EXECUTABLES:
        raise ConfigError("SEXTANT_ROLLBACK_COMMAND cannot be a no-op command.")
    if target_version not in parts and target_version not in command_text:
        raise ConfigError("SEXTANT_ROLLBACK_COMMAND must include the target version.")
    return parts


def _validate_runbook_ref(value: str) -> str:
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme == "runbook" and (parsed.netloc or parsed.path.lstrip("/")):
        return scheme
    if scheme == "https" and (parsed.netloc or parsed.path.lstrip("/")):
        _validate_hosted_https_url("SEXTANT_ROLLBACK_RUNBOOK_REF", value)
        return scheme
    raise ConfigError(
        "SEXTANT_ROLLBACK_RUNBOOK_REF must be an auditable runbook:// or hosted https:// reference."
    )


def _validate_hosted_https_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if parsed.scheme != "https" or not host:
        raise ConfigError(f"{name} must be a hosted HTTPS URL.")
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
        raise ConfigError(f"{name} is required for hosted rollback drill proof.")
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


def _status_hash(payload: Mapping[str, object]) -> str:
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
