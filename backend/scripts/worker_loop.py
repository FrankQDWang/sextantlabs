from __future__ import annotations

import os
import signal
import sys
import time
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sextant.common.observability import MetricsRegistry  # noqa: E402
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
from sextant.infra.worker import DbWorker, release_timed_out_jobs  # noqa: E402
from sextant.infra.worker_handlers import build_worker_handlers  # noqa: E402
from sextant.infra.worker_metrics import start_worker_metrics_server  # noqa: E402


def main() -> None:
    database_url = database_url_from_env()
    object_store = object_store_from_uri(object_store_uri_from_env())
    metrics = MetricsRegistry()
    story_draft_provider = story_draft_provider_from_env(metrics=metrics)
    pov_detection_provider = pov_detection_provider_from_env(metrics=metrics)
    event_aggregation_provider = event_aggregation_provider_from_env(metrics=metrics)
    memory_extraction_provider = memory_extraction_provider_from_env(metrics=metrics)
    embedding_provider = embedding_provider_from_env(metrics=metrics)
    interval_seconds = float(os.environ.get("SEXTANT_WORKER_POLL_SECONDS", "0.5"))
    worker_id = os.environ.get("SEXTANT_WORKER_ID", "local-worker")
    engine = create_engine(database_url)
    metrics_server = _start_metrics_server(metrics)
    running = True

    def stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        while running:
            with Session(engine) as session:
                release_timed_out_jobs(
                    session,
                    now=datetime.now(UTC),
                    lease_timeout=timedelta(minutes=5),
                )
                worker = DbWorker(
                    session,
                    build_worker_handlers(
                        object_store,
                        story_draft_provider,
                        pov_detection_provider,
                        event_aggregation_provider=event_aggregation_provider,
                        memory_extraction_provider=memory_extraction_provider,
                        embedding_provider=embedding_provider,
                    ),
                    metrics=metrics,
                )
                processed = worker.run_once(worker_id=worker_id)
            if not processed:
                time.sleep(interval_seconds)
    finally:
        if metrics_server is not None:
            metrics_server.shutdown()
            metrics_server.server_close()


def _start_metrics_server(metrics: MetricsRegistry) -> ThreadingHTTPServer | None:
    raw_port = os.environ.get("SEXTANT_WORKER_METRICS_PORT", "").strip()
    if not raw_port:
        return None
    return start_worker_metrics_server(
        metrics,
        host=os.environ.get("SEXTANT_WORKER_METRICS_HOST", "127.0.0.1"),
        port=int(raw_port),
    )


if __name__ == "__main__":
    main()
