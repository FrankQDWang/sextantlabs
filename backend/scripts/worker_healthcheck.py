from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sextant.infra.embedding_provider import embedding_provider_from_env  # noqa: E402
from sextant.infra.event_aggregation_provider import (  # noqa: E402
    event_aggregation_provider_from_env,
)
from sextant.infra.memory_extraction_provider import (  # noqa: E402
    memory_extraction_provider_from_env,
)
from sextant.infra.object_store import object_store_from_uri  # noqa: E402
from sextant.infra.pov_detection_provider import pov_detection_provider_from_env  # noqa: E402
from sextant.infra.runtime_config import (  # noqa: E402
    database_url_from_env,
    object_store_uri_from_env,
)
from sextant.infra.story_draft_provider import story_draft_provider_from_env  # noqa: E402
from sextant.infra.worker_handlers import build_worker_handlers  # noqa: E402
from sextant.infra.worker_health import worker_health_report  # noqa: E402


def main() -> None:
    try:
        database_url = database_url_from_env()
        object_store = object_store_from_uri(object_store_uri_from_env())
        handlers = build_worker_handlers(
            object_store,
            story_draft_provider_from_env(),
            pov_detection_provider_from_env(),
            event_aggregation_provider=event_aggregation_provider_from_env(),
            memory_extraction_provider=memory_extraction_provider_from_env(),
            embedding_provider=embedding_provider_from_env(),
        )
        engine = create_engine(database_url)
        with Session(engine) as session:
            report = worker_health_report(session, handlers)
    except Exception as exc:
        report = {
            "status": "fail",
            "database": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
