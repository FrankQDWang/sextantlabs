from __future__ import annotations

import os

from sextant.infra.provider_runtime import release_environment_is_production

DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./.sextant/local.db"
DEFAULT_OBJECT_STORE_ROOT = "./.sextant/objects"


def database_url_from_env(*, default: str = DEFAULT_DATABASE_URL) -> str:
    value = os.environ.get("SEXTANT_DATABASE_URL", "").strip()
    if not value:
        if release_environment_is_production():
            raise RuntimeError(
                "SEXTANT_DATABASE_URL is required when SEXTANT_RELEASE_ENVIRONMENT=production."
            )
        return default
    return validate_database_url_for_release(value)


def object_store_uri_from_env(*, default: str = DEFAULT_OBJECT_STORE_ROOT) -> str:
    value = os.environ.get("SEXTANT_OBJECT_STORE_ROOT", "").strip()
    if not value:
        if release_environment_is_production():
            raise RuntimeError(
                "SEXTANT_OBJECT_STORE_ROOT is required when SEXTANT_RELEASE_ENVIRONMENT=production."
            )
        return default
    return validate_object_store_uri_for_release(value)


def validate_database_url_for_release(database_url: str) -> str:
    if release_environment_is_production() and not database_url.startswith("postgresql"):
        raise RuntimeError(
            "SEXTANT_DATABASE_URL must be a PostgreSQL URL when "
            "SEXTANT_RELEASE_ENVIRONMENT=production."
        )
    return database_url


def validate_object_store_uri_for_release(object_store_uri: str) -> str:
    if release_environment_is_production() and not object_store_uri.startswith("s3://"):
        raise RuntimeError(
            "SEXTANT_OBJECT_STORE_ROOT must be an s3:// URI when "
            "SEXTANT_RELEASE_ENVIRONMENT=production."
        )
    return object_store_uri
