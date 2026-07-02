from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

WORKER_JOBS_TOTAL = "sextant_worker_jobs_total"
QUEUE_AGE_COUNT = "sextant_job_queue_age_seconds_count"
QUEUE_AGE_SUM = "sextant_job_queue_age_seconds_sum"
METRIC_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+(?P<value>[-+0-9.eE]+)$"
)
LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"')


class ConfigError(RuntimeError):
    pass


class CapacityError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerCapacityConfig:
    metrics_url: str
    bearer_token: str | None
    timeout_seconds: float
    max_queue_age_seconds: float
    min_succeeded_jobs: float

    @classmethod
    def from_env(cls, env: dict[str, str]) -> WorkerCapacityConfig:
        metrics_url = _required(env, "SEXTANT_HOSTED_WORKER_METRICS_URL")
        _validate_hosted_https_url("SEXTANT_HOSTED_WORKER_METRICS_URL", metrics_url)
        return cls(
            metrics_url=metrics_url,
            bearer_token=_optional(env, "SEXTANT_HOSTED_WORKER_METRICS_BEARER_TOKEN"),
            timeout_seconds=_positive_float(
                env.get("SEXTANT_WORKER_CAPACITY_TIMEOUT_SECONDS", "10"),
                "SEXTANT_WORKER_CAPACITY_TIMEOUT_SECONDS",
            ),
            max_queue_age_seconds=_positive_float(
                env.get("SEXTANT_WORKER_CAPACITY_MAX_QUEUE_AGE_SECONDS", "300"),
                "SEXTANT_WORKER_CAPACITY_MAX_QUEUE_AGE_SECONDS",
            ),
            min_succeeded_jobs=_positive_float(
                env.get("SEXTANT_WORKER_CAPACITY_MIN_SUCCEEDED_JOBS", "1"),
                "SEXTANT_WORKER_CAPACITY_MIN_SUCCEEDED_JOBS",
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe hosted Sextant worker capacity through Prometheus metrics."
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate worker capacity probe configuration without network requests.",
    )
    args = parser.parse_args()
    try:
        config = WorkerCapacityConfig.from_env(dict(os.environ))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if args.check_config:
        print("hosted-worker-capacity-config-ok")
        return
    try:
        metrics_text = fetch_metrics(config)
        result = evaluate_worker_metrics(metrics_text, config)
    except (CapacityError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def fetch_metrics(config: WorkerCapacityConfig) -> str:
    headers = {"Accept": "text/plain"}
    if config.bearer_token is not None:
        headers["Authorization"] = f"Bearer {config.bearer_token}"
    request = Request(config.metrics_url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Worker metrics probe failed with HTTP {exc.code}: {body}") from exc


def evaluate_worker_metrics(
    metrics_text: str,
    config: WorkerCapacityConfig,
) -> dict[str, object]:
    samples = parse_prometheus_metrics(metrics_text)
    succeeded_jobs = sum(
        sample["value"]
        for sample in samples
        if sample["name"] == WORKER_JOBS_TOTAL and sample["labels"].get("status") == "succeeded"
    )
    failed_terminal_jobs = sum(
        sample["value"]
        for sample in samples
        if sample["name"] == WORKER_JOBS_TOTAL
        and sample["labels"].get("status") == "failed_terminal"
    )
    if succeeded_jobs < config.min_succeeded_jobs:
        raise CapacityError(
            "Hosted worker capacity probe found "
            f"{succeeded_jobs:g} succeeded jobs; expected at least "
            f"{config.min_succeeded_jobs:g}."
        )
    max_average_queue_age = _max_average_queue_age(samples)
    if max_average_queue_age > config.max_queue_age_seconds:
        raise CapacityError(
            "Hosted worker queue age is too high: "
            f"{max_average_queue_age:g}s average exceeds "
            f"{config.max_queue_age_seconds:g}s."
        )
    return {
        "status": "pass",
        "worker_metrics_url": config.metrics_url,
        "succeeded_jobs": succeeded_jobs,
        "failed_terminal_jobs": failed_terminal_jobs,
        "max_average_queue_age_seconds": max_average_queue_age,
        "metric_series_count": len(samples),
    }


def parse_prometheus_metrics(metrics_text: str) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for raw_line in metrics_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = METRIC_RE.match(line)
        if match is None:
            continue
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        samples.append(
            {
                "name": match.group("name"),
                "labels": _parse_labels(match.group("labels") or ""),
                "value": value,
            }
        )
    return samples


def _max_average_queue_age(samples: list[dict[str, Any]]) -> float:
    counts: dict[str, float] = {}
    sums: dict[str, float] = {}
    for sample in samples:
        job_type = str(sample["labels"].get("job_type") or "")
        if not job_type:
            continue
        if sample["name"] == QUEUE_AGE_COUNT:
            counts[job_type] = counts.get(job_type, 0) + sample["value"]
        if sample["name"] == QUEUE_AGE_SUM:
            sums[job_type] = sums.get(job_type, 0) + sample["value"]
    averages = [
        sums[job_type] / count
        for job_type, count in counts.items()
        if count > 0 and job_type in sums
    ]
    return max(averages, default=0.0)


def _parse_labels(raw_labels: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2).replace(r"\"", '"').replace(r"\\", "\\")
        for match in LABEL_RE.finditer(raw_labels)
    }


def _required(env: dict[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required for hosted worker capacity probe.")
    return value


def _optional(env: dict[str, str], name: str) -> str | None:
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


def _validate_hosted_https_url(name: str, value: str) -> None:
    parsed = urlparse(value)
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if parsed.scheme != "https" or not host:
        raise ConfigError(f"{name} must be a hosted HTTPS URL.")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local host.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local address.")


if __name__ == "__main__":
    main()
