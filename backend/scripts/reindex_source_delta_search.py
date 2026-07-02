from __future__ import annotations

import argparse

from sextant.infra.runtime_config import (
    database_url_from_env,
    object_store_uri_from_env,
    validate_database_url_for_release,
    validate_object_store_uri_for_release,
)
from sextant.infra.source_delta_search import reindex_source_delta_search


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild SourceDelta submitted-text search indexes from object storage."
    )
    parser.add_argument(
        "--database-url",
    )
    parser.add_argument(
        "--object-store-root",
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--all", action="store_true", help="Rebuild rows that already have text.")
    args = parser.parse_args()
    try:
        database_url = (
            validate_database_url_for_release(args.database_url)
            if args.database_url is not None
            else database_url_from_env()
        )
        object_store_root = (
            validate_object_store_uri_for_release(args.object_store_root)
            if args.object_store_root is not None
            else object_store_uri_from_env()
        )
    except RuntimeError as exc:
        parser.error(str(exc))

    count = reindex_source_delta_search(
        database_url=database_url,
        object_store_root=object_store_root,
        batch_size=args.batch_size,
        rebuild_all=args.all,
    )
    print(f"source-delta-search-reindexed rows={count}")


if __name__ == "__main__":
    main()
