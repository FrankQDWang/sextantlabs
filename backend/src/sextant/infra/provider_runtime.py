import os
from typing import Any

LOCAL_PROVIDER_VALUES = {"local", "local-deterministic"}
PRODUCTION_ENVIRONMENTS = {"production", "prod"}


def release_environment_is_production() -> bool:
    release_environment = os.environ.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip().lower()
    return release_environment in PRODUCTION_ENVIRONMENTS


def reject_local_provider_in_production(config_name: str, provider: str) -> None:
    if provider not in LOCAL_PROVIDER_VALUES:
        return
    if not release_environment_is_production():
        return
    raise RuntimeError(
        f"{config_name} must not be {provider!r} when SEXTANT_RELEASE_ENVIRONMENT=production."
    )


def reject_implicit_local_provider_default_in_production(parameter_name: str) -> None:
    if not release_environment_is_production():
        return
    raise RuntimeError(
        f"{parameter_name} must be explicitly configured with a non-local provider when "
        "SEXTANT_RELEASE_ENVIRONMENT=production."
    )


def reject_local_provider_instance_in_production(parameter_name: str, provider: Any) -> None:
    if not release_environment_is_production():
        return
    provider_type = type(provider)
    if not provider_type.__module__.startswith("sextant.skills.local_"):
        return
    raise RuntimeError(
        f"{parameter_name} must not use deterministic local provider "
        f"{provider_type.__name__} when SEXTANT_RELEASE_ENVIRONMENT=production."
    )
