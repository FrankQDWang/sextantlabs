from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy import and_, create_engine, or_
from sqlalchemy.orm import Session

from sextant.infra.db.models import SourceDeltaRecord
from sextant.infra.object_store import object_store_from_uri


def source_delta_search_text(text: str) -> str:
    return " ".join(text.casefold().split())


def reindex_source_delta_search(
    *,
    database_url: str,
    object_store_root: str,
    batch_size: int = 100,
    rebuild_all: bool = False,
) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be positive.")
    engine = _engine(database_url)
    object_store = object_store_from_uri(object_store_root)
    updated_count = 0
    after_created_at = None
    after_id: UUID | None = None
    with Session(engine) as session:
        while True:
            query = session.query(SourceDeltaRecord).order_by(
                SourceDeltaRecord.created_at,
                SourceDeltaRecord.id,
            )
            if after_created_at is not None and after_id is not None:
                query = query.filter(
                    or_(
                        SourceDeltaRecord.created_at > after_created_at,
                        and_(
                            SourceDeltaRecord.created_at == after_created_at,
                            SourceDeltaRecord.id > after_id,
                        ),
                    )
                )
            if not rebuild_all:
                query = query.filter(SourceDeltaRecord.submitted_text_search == "")
            batch = query.limit(batch_size).all()
            if not batch:
                break
            for delta in batch:
                text = object_store.get_text(delta.submitted_text_ref)
                delta.submitted_text_search = source_delta_search_text(text)
                updated_count += 1
            after_created_at = batch[-1].created_at
            after_id = batch[-1].id
            session.commit()
    return updated_count


def _engine(database_url: str):
    if database_url.startswith("sqlite"):
        sqlite_path = database_url.removeprefix("sqlite+pysqlite:///")
        if sqlite_path and sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(database_url, connect_args={"check_same_thread": False})
    return create_engine(database_url, pool_pre_ping=True)
