from __future__ import annotations

import json
import os
import sys
import tempfile
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sextant.infra.db.models import (  # noqa: E402
    Project,
    ProjectMembership,
    RawSource,
    SourceDeltaRecord,
    SourceVersion,
)
from sextant.infra.object_store import LocalObjectStore  # noqa: E402
from sextant.infra.provider_runtime import release_environment_is_production  # noqa: E402
from sextant.infra.worker import DbWorker  # noqa: E402
from sextant.infra.worker_handlers import build_worker_handlers  # noqa: E402
from sextant.skills.local_embedding import LocalEmbeddingProvider  # noqa: E402
from sextant.skills.local_story_draft import LocalStoryDraftProvider  # noqa: E402

MANUSCRIPT = "\n".join(
    [
        "Mira 把空的地图筒推过桌面。",
        "她把钥匙放在两人之间。钥匙是冷的，比这间屋子里任何东西都冷。",
    ]
)


def main() -> None:
    if release_environment_is_production():
        raise SystemExit(
            "backend/scripts/production_smoke.py is a local production-path smoke; "
            "do not run it with SEXTANT_RELEASE_ENVIRONMENT=production. Use hosted "
            "readiness and external smoke gates for production releases."
        )
    external_database_url = os.environ.get("SEXTANT_SMOKE_DATABASE_URL")
    external_object_root = os.environ.get("SEXTANT_SMOKE_OBJECT_STORE_ROOT")
    if external_database_url:
        if external_object_root:
            object_root = Path(external_object_root)
            object_root.mkdir(parents=True, exist_ok=True)
            result = run_smoke(external_database_url, object_root)
        else:
            with tempfile.TemporaryDirectory(prefix="sextant-smoke-objects-") as tmp:
                result = run_smoke(external_database_url, Path(tmp))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return

    with tempfile.TemporaryDirectory(prefix="sextant-smoke-") as tmp:
        tmp_path = Path(tmp)
        database_url = f"sqlite+pysqlite:///{tmp_path / 'smoke.db'}"
        object_root = tmp_path / "objects"
        result = run_smoke(database_url, object_root)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def run_smoke(database_url: str, object_root: Path) -> dict[str, object]:
    os.environ["SEXTANT_DATABASE_URL"] = database_url
    os.environ["SEXTANT_OBJECT_STORE_ROOT"] = str(object_root)
    os.environ["SEXTANT_AUTH_MODE"] = "header-dev"

    command.upgrade(Config("alembic.ini"), "head")

    object_store = LocalObjectStore(object_root)
    project_id, actor_id, source_id, version_id = _seed(database_url, object_store)

    from sextant.runtime import build_app

    client = TestClient(build_app())
    headers = {
        "X-Actor-Id": str(actor_id),
        "X-Request-Id": "req-smoke-action",
        "Idempotency-Key": "idem-smoke-action",
    }
    source = client.get(
        f"/api/projects/{project_id}/sources/{source_id}/versions/{version_id}",
        headers={"X-Actor-Id": str(actor_id)},
    )
    source.raise_for_status()

    action = client.post(
        f"/api/projects/{project_id}/action-requests",
        headers=headers,
        json={
            "source_id": str(source_id),
            "source_version_id": str(version_id),
            "trigger": "selection",
            "action_type": "rewrite_span",
            "target": {
                "kind": "selected_text",
                "source_id": str(source_id),
                "source_version_id": str(version_id),
                "range": {"start": 0, "end": 16},
                "selected_text": "Mira 把空的地图筒",
            },
            "constraints": {"smoke": True},
            "expected_output": "draft_candidate",
            "actor_intent": "改写得更克制",
        },
    )
    action.raise_for_status()
    action_request_id = action.json()["action_request_id"]

    run = client.post(
        f"/api/projects/{project_id}/action-requests/{action_request_id}/run",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-smoke-run",
            "Idempotency-Key": "idem-smoke-run",
        },
        json={"current_text_window": source.json()["text"]},
    )
    run.raise_for_status()
    candidate_id = run.json()["draft_candidate_ids"][0]

    candidate = client.get(
        f"/api/projects/{project_id}/candidates/{candidate_id}",
        headers={"X-Actor-Id": str(actor_id)},
    )
    candidate.raise_for_status()

    review = client.post(
        f"/api/projects/{project_id}/agent/check-risk",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-smoke-check-risk",
            "Idempotency-Key": "idem-smoke-check-risk",
        },
        json={
            "trigger": "toolbar",
            "target": {"kind": "candidate", "candidate_id": str(candidate_id)},
            "constraints": {"smoke": True},
            "actor_intent": "检查候选风险",
            "source_id": str(source_id),
            "source_version_id": str(version_id),
            "current_text_window": "这句写成 risk-context 已经坐实了秘密。",
        },
    )
    review.raise_for_status()
    review_body = review.json()
    assert review_body["output_type"] == "risk_findings"
    assert review_body["risk_finding_ids"], "expected smoke candidate review finding"
    assert review_body["risk_findings"][0]["draft_local_only"] is True

    accept = client.post(
        f"/api/projects/{project_id}/candidates/{candidate_id}/accept",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-smoke-accept",
            "Idempotency-Key": "idem-smoke-accept",
        },
        json={
            "accepted_text": "FACT: character:mira | owns | object:lantern-map | low",
            "accept_mode": "partial",
            "target_source_id": str(source_id),
            "target_version_id": str(version_id),
            "insert_or_replace_range": {"start": 0, "end": 16},
            "base_hash": candidate.json()["base_hash"],
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "author_edited": True,
        },
    )
    accept.raise_for_status()
    source_delta_id = UUID(accept.json()["source_delta_id"])

    engine = create_engine(database_url)
    handlers = build_worker_handlers(
        object_store,
        LocalStoryDraftProvider(),
        embedding_provider=LocalEmbeddingProvider(),
    )
    completed = False
    for _ in range(20):
        with Session(engine) as session:
            worker = DbWorker(session, handlers)
            processed = worker.run_once(worker_id="smoke-worker")
            delta = session.get(SourceDeltaRecord, source_delta_id)
            completed = delta is not None and delta.status == "memory_writeback_completed"
        if completed and not processed:
            break
        if not processed:
            break
    if not completed:
        raise AssertionError("worker did not complete memory writeback during smoke")

    preview = client.get(
        "/api/projects/"
        f"{project_id}/source-deltas/{accept.json()['source_delta_id']}"
        "/memory-writeback-preview",
        headers={"X-Actor-Id": str(actor_id)},
    )
    preview.raise_for_status()
    preview_body = preview.json()
    assert preview_body["source_delta_status"] == "memory_writeback_completed"
    assert preview_body["source_spans"], "expected SourceSpan in preview"
    assert preview_body["evidence_log_entries"], "expected EvidenceLogEntry in preview"
    assert preview_body["fact_assertions"], "expected FactAssertion in preview"
    assert preview_body["memory_pages"], "expected MemoryPage in preview"
    assert preview_body["graph_edges"], "expected GraphProjection edge in preview"

    answer = client.post(
        f"/api/projects/{project_id}/memory/answer",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-smoke-memory-answer",
            "Idempotency-Key": "idem-smoke-memory-answer",
        },
        json={
            "question": "米拉拥有什么？",
            "subject_ref": {"type": "character", "id": "mira"},
            "predicate": "owns",
        },
    )
    answer.raise_for_status()
    answer_body = answer.json()
    assert answer_body["answer_type"] == "canon"
    assert answer_body["source_span_refs"], "expected evidence-backed memory answer"

    return {
        "status": "pass",
        "project_id": str(project_id),
        "source_delta_id": accept.json()["source_delta_id"],
        "job_id": accept.json()["memory_writeback_job_id"],
        "review_finding_count": len(review_body["risk_finding_ids"]),
        "memory_answer_type": answer_body["answer_type"],
        "memory_answer_source_span_count": len(answer_body["source_span_refs"]),
        "source_span_count": len(preview_body["source_spans"]),
        "fact_count": len(preview_body["fact_assertions"]),
        "graph_edge_count": len(preview_body["graph_edges"]),
    }


def _seed(database_url: str, object_store: LocalObjectStore):
    project_id = uuid4()
    actor_id = uuid4()
    source_id = uuid4()
    version_id = uuid4()
    raw_text_ref = object_store.put_text("raw/smoke-chapter.txt", MANUSCRIPT)
    with Session(create_engine(database_url)) as session:
        session.add_all(
            [
                Project(id=project_id, name="Smoke Harbor"),
                ProjectMembership(
                    id=uuid4(),
                    project_id=project_id,
                    actor_id=actor_id,
                    role="owner",
                    status="active",
                ),
                RawSource(
                    id=source_id,
                    project_id=project_id,
                    source_type="draft_manuscript",
                    source_scope="user_draft",
                    title="Smoke Chapter",
                    ownership_status="owned",
                    raw_text_ref=raw_text_ref,
                ),
                SourceVersion(
                    id=version_id,
                    source_id=source_id,
                    version_label="v1",
                    raw_hash=sha256(MANUSCRIPT.encode("utf-8")).hexdigest(),
                    raw_text_ref=raw_text_ref,
                ),
            ]
        )
        session.commit()
    return project_id, actor_id, source_id, version_id


if __name__ == "__main__":
    main()
