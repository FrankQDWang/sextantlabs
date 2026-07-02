from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sextant.infra.db.models import Base, Project, RawSource, SourceDeltaRecord, SourceVersion
from sextant.infra.object_store import LocalObjectStore
from sextant.infra.source_delta_search import reindex_source_delta_search
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_reindex_source_delta_search_rebuilds_from_object_store(tmp_path) -> None:
    database_path = tmp_path / "search.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    object_store = LocalObjectStore(tmp_path / "objects")
    text_ref = object_store.put_text("deltas/one.txt", "Mira keeps the Lantern Map.")

    project_id = uuid4()
    source_id = uuid4()
    version_id = uuid4()
    delta_id = uuid4()
    with Session(engine) as session:
        session.add(Project(id=project_id, name="Harbor Nine"))
        session.add(
            RawSource(
                id=source_id,
                project_id=project_id,
                source_type="draft_manuscript",
                source_scope="user_draft",
                title="Chapter 3",
                ownership_status="owned",
                raw_text_ref=text_ref,
            )
        )
        session.add(
            SourceVersion(
                id=version_id,
                source_id=source_id,
                version_label="v1",
                raw_hash="hash-v1",
                raw_text_ref=text_ref,
            )
        )
        session.add(
            SourceDeltaRecord(
                id=delta_id,
                project_id=project_id,
                source_id=source_id,
                previous_version_id=version_id,
                new_version_id=None,
                accepted_fragment_id=None,
                delta_kind="insert",
                range_start=0,
                range_end=0,
                base_hash="hash-v1",
                submitted_text_ref=text_ref,
                submitted_text_search="",
                source_type="draft_manuscript",
                source_scope="user_draft",
                provenance={},
                status="memory_writeback_queued",
            )
        )
        session.commit()

    updated = reindex_source_delta_search(
        database_url=database_url,
        object_store_root=str(tmp_path / "objects"),
    )

    assert updated == 1
    with Session(engine) as session:
        delta = session.get(SourceDeltaRecord, delta_id)
        assert delta is not None
        assert delta.submitted_text_search == "mira keeps the lantern map."


def test_reindex_source_delta_search_rebuild_all_advances_batches(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "search-all.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)

    ref_one = "object://fake/deltas/one.txt"
    ref_two = "object://fake/deltas/two.txt"
    fake_store = _CountingObjectStore(
        {
            ref_one: "Mira keeps the Lantern Map.",
            ref_two: "Kestrel hides the cold key.",
        },
        max_reads=2,
    )
    monkeypatch.setattr(
        "sextant.infra.source_delta_search.object_store_from_uri",
        lambda _uri: fake_store,
    )

    project_id = uuid4()
    source_id = uuid4()
    version_id = uuid4()
    first_delta_id = uuid4()
    second_delta_id = uuid4()
    created_at = datetime(2026, 7, 1, tzinfo=UTC)
    with Session(engine) as session:
        session.add(Project(id=project_id, name="Harbor Nine"))
        session.add(
            RawSource(
                id=source_id,
                project_id=project_id,
                source_type="draft_manuscript",
                source_scope="user_draft",
                title="Chapter 3",
                ownership_status="owned",
                raw_text_ref=ref_one,
            )
        )
        session.add(
            SourceVersion(
                id=version_id,
                source_id=source_id,
                version_label="v1",
                raw_hash="hash-v1",
                raw_text_ref=ref_one,
            )
        )
        session.add_all(
            [
                _source_delta(
                    first_delta_id,
                    project_id=project_id,
                    source_id=source_id,
                    version_id=version_id,
                    submitted_text_ref=ref_one,
                    submitted_text_search="stale one",
                    created_at=created_at,
                ),
                _source_delta(
                    second_delta_id,
                    project_id=project_id,
                    source_id=source_id,
                    version_id=version_id,
                    submitted_text_ref=ref_two,
                    submitted_text_search="stale two",
                    created_at=created_at + timedelta(seconds=1),
                ),
            ]
        )
        session.commit()

    updated = reindex_source_delta_search(
        database_url=database_url,
        object_store_root="object://fake",
        batch_size=1,
        rebuild_all=True,
    )

    assert updated == 2
    assert fake_store.read_refs == [ref_one, ref_two]
    with Session(engine) as session:
        first_delta = session.get(SourceDeltaRecord, first_delta_id)
        second_delta = session.get(SourceDeltaRecord, second_delta_id)
        assert first_delta is not None
        assert second_delta is not None
        assert first_delta.submitted_text_search == "mira keeps the lantern map."
        assert second_delta.submitted_text_search == "kestrel hides the cold key."


def test_reindex_script_rejects_local_defaults_in_production(tmp_path) -> None:
    result = _run_reindex_script(
        tmp_path,
        env_overrides={"SEXTANT_RELEASE_ENVIRONMENT": "production"},
        drop_env={"SEXTANT_DATABASE_URL", "SEXTANT_OBJECT_STORE_ROOT"},
    )

    assert result.returncode != 0
    assert "SEXTANT_DATABASE_URL" in result.stderr


def test_reindex_script_rejects_local_object_store_arg_in_production(tmp_path) -> None:
    result = _run_reindex_script(
        tmp_path,
        args=[
            "--database-url",
            "postgresql+psycopg://sextant:sextant@example.invalid:5432/sextant",
            "--object-store-root",
            str(tmp_path / "objects"),
        ],
        env_overrides={"SEXTANT_RELEASE_ENVIRONMENT": "production"},
    )

    assert result.returncode != 0
    assert "SEXTANT_OBJECT_STORE_ROOT" in result.stderr


class _CountingObjectStore:
    def __init__(self, texts: dict[str, str], *, max_reads: int) -> None:
        self._texts = texts
        self._max_reads = max_reads
        self.read_refs: list[str] = []

    def get_text(self, ref: str) -> str:
        self.read_refs.append(ref)
        if len(self.read_refs) > self._max_reads:
            raise AssertionError("reindex_source_delta_search did not advance batches")
        return self._texts[ref]


def _source_delta(
    delta_id,
    *,
    project_id,
    source_id,
    version_id,
    submitted_text_ref: str,
    submitted_text_search: str,
    created_at: datetime,
) -> SourceDeltaRecord:
    return SourceDeltaRecord(
        id=delta_id,
        project_id=project_id,
        source_id=source_id,
        previous_version_id=version_id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="insert",
        range_start=0,
        range_end=0,
        base_hash="hash-v1",
        submitted_text_ref=submitted_text_ref,
        submitted_text_search=submitted_text_search,
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={},
        status="memory_writeback_queued",
        created_at=created_at,
    )


def _run_reindex_script(
    cwd: Path,
    *,
    args: list[str] | None = None,
    env_overrides: dict[str, str] | None = None,
    drop_env: set[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("backend/src").resolve())
    for key in drop_env or set():
        env.pop(key, None)
    env.update(env_overrides or {})
    return subprocess.run(
        [
            sys.executable,
            str(Path("backend/scripts/reindex_source_delta_search.py").resolve()),
            *(args or []),
        ],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
