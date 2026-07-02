from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_REQUIRED_METRICS = (
    "sextant_api_requests_total",
    "sextant_worker_jobs_total",
)
METRIC_NAME_RE = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)")
METRIC_VALUE_RE = re.compile(r"\s[-+0-9.eE]+(?:\s+\d+)?$")


class ConfigError(RuntimeError):
    pass


class ObservabilityProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class EndpointResponse:
    status_code: int
    body: bytes


@dataclass(frozen=True)
class ObservabilityPipelineConfig:
    metrics_url: str
    traces_url: str
    alerts_url: str
    bearer_token: str | None
    timeout_seconds: float
    required_metrics: tuple[str, ...]
    traces_expect: str | None
    alerts_expect: str | None

    @classmethod
    def from_env(cls, env: dict[str, str]) -> ObservabilityPipelineConfig:
        release_environment = _required(env, "SEXTANT_RELEASE_ENVIRONMENT")
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT must be production for hosted "
                "observability pipeline probe."
            )
        metrics_url = _required(env, "SEXTANT_HOSTED_METRICS_URL")
        traces_url = _required(env, "SEXTANT_HOSTED_TRACES_URL")
        alerts_url = _required(env, "SEXTANT_ALERTING_DASHBOARD_URL")
        _validate_hosted_https_url("SEXTANT_HOSTED_METRICS_URL", metrics_url)
        _validate_hosted_https_url("SEXTANT_HOSTED_TRACES_URL", traces_url)
        _validate_hosted_https_url("SEXTANT_ALERTING_DASHBOARD_URL", alerts_url)
        return cls(
            metrics_url=metrics_url,
            traces_url=traces_url,
            alerts_url=alerts_url,
            bearer_token=_optional(env, "SEXTANT_OBSERVABILITY_PIPELINE_BEARER_TOKEN"),
            timeout_seconds=_positive_float(
                env.get("SEXTANT_OBSERVABILITY_PROBE_TIMEOUT_SECONDS", "10"),
                "SEXTANT_OBSERVABILITY_PROBE_TIMEOUT_SECONDS",
            ),
            required_metrics=_required_metrics(env),
            traces_expect=_optional(env, "SEXTANT_OBSERVABILITY_TRACES_EXPECT"),
            alerts_expect=_optional(env, "SEXTANT_OBSERVABILITY_ALERTS_EXPECT"),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Probe hosted Sextant observability surfaces and emit sanitized JSON evidence."
        )
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate observability probe configuration without network requests.",
    )
    args = parser.parse_args()
    try:
        config = ObservabilityPipelineConfig.from_env(dict(os.environ))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if args.check_config:
        print("hosted-observability-pipeline-config-ok")
        return
    try:
        result = run_observability_probe(config)
    except (ObservabilityProbeError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def run_observability_probe(
    config: ObservabilityPipelineConfig,
    *,
    fetcher: Callable[[str, ObservabilityPipelineConfig], EndpointResponse] | None = None,
) -> dict[str, object]:
    fetch = fetcher or fetch_endpoint
    metrics_response = fetch(config.metrics_url, config)
    traces_response = fetch(config.traces_url, config)
    alerts_response = fetch(config.alerts_url, config)

    _validate_endpoint_response("metrics", metrics_response, expected=None)
    _validate_endpoint_response("traces", traces_response, expected=config.traces_expect)
    _validate_endpoint_response("alerts", alerts_response, expected=config.alerts_expect)
    parsed_metrics = _parse_metric_names(metrics_response.body.decode("utf-8", errors="replace"))
    found = [metric for metric in config.required_metrics if metric in parsed_metrics]
    missing = [metric for metric in config.required_metrics if metric not in parsed_metrics]
    if missing:
        raise ObservabilityProbeError(
            "Hosted observability metrics response is missing required metrics: "
            + ", ".join(missing)
        )

    return {
        "status": "pass",
        "endpoints": {
            "metrics_url": config.metrics_url,
            "traces_url": config.traces_url,
            "alerts_url": config.alerts_url,
        },
        "metrics": {
            **_endpoint_evidence(metrics_response),
            "required_found": found,
            "series_count": len(parsed_metrics),
        },
        "traces": _endpoint_evidence(traces_response),
        "alerts": _endpoint_evidence(alerts_response),
    }


def fetch_endpoint(url: str, config: ObservabilityPipelineConfig) -> EndpointResponse:
    headers = {"Accept": "text/plain, application/json, text/html;q=0.8"}
    if config.bearer_token is not None:
        headers["Authorization"] = f"Bearer {config.bearer_token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            status_code = getattr(response, "status", response.getcode())
            return EndpointResponse(status_code=int(status_code), body=response.read())
    except HTTPError as exc:
        raise RuntimeError(f"Hosted observability endpoint returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(f"Hosted observability endpoint request failed: {exc.reason}") from exc


def _validate_endpoint_response(
    kind: str,
    response: EndpointResponse,
    *,
    expected: str | None,
) -> None:
    if response.status_code < 200 or response.status_code >= 300:
        raise ObservabilityProbeError(
            f"Hosted observability {kind} response returned HTTP {response.status_code}."
        )
    if not response.body:
        raise ObservabilityProbeError(f"Hosted observability {kind} response is empty.")
    if expected is None:
        return
    text = response.body.decode("utf-8", errors="replace")
    if expected not in text:
        raise ObservabilityProbeError(
            f"Hosted observability {kind} response did not contain expected marker."
        )


def _endpoint_evidence(response: EndpointResponse) -> dict[str, object]:
    return {
        "status_code": response.status_code,
        "body_bytes": len(response.body),
        "body_sha256": hashlib.sha256(response.body).hexdigest(),
    }


def _parse_metric_names(metrics_text: str) -> list[str]:
    names: list[str] = []
    for raw_line in metrics_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = _metric_name_from_line(line)
        if name is None:
            continue
        names.append(name)
    return names


def _metric_name_from_line(line: str) -> str | None:
    name_match = METRIC_NAME_RE.match(line)
    if name_match is None:
        return None
    name = name_match.group("name")
    remainder = line[name_match.end() :]
    if not remainder or remainder[0] not in {"{", " ", "\t"}:
        return None
    if METRIC_VALUE_RE.search(line) is None:
        return None
    return name


def _required_metrics(env: dict[str, str]) -> tuple[str, ...]:
    raw_value = env.get("SEXTANT_OBSERVABILITY_REQUIRED_METRICS")
    if raw_value is None:
        return DEFAULT_REQUIRED_METRICS
    metrics = tuple(metric.strip() for metric in raw_value.split(",") if metric.strip())
    if not metrics:
        raise ConfigError("SEXTANT_OBSERVABILITY_REQUIRED_METRICS must list metric names.")
    return metrics


def _required(env: dict[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required for hosted observability pipeline probe.")
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
