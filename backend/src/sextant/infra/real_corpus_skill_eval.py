from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sextant.infra.db.models import (
    Base,
    FactAssertionRecord,
    GraphProjectionEdge,
    JobRecord,
    MemoryPage,
    Project,
    RawSource,
    ReviewItemRecord,
    SkillRun,
    SourceDeltaRecord,
    SourceSpan,
    SourceVersion,
)
from sextant.infra.memory_writeback import MemoryWritebackHandler
from sextant.infra.object_store import LocalObjectStore
from sextant.skills.local_memory_extractor import LocalMemoryExtractionProvider


@dataclass(frozen=True, slots=True)
class RealCorpusEvalCase:
    case_id: str
    line_start: int
    line_end: int
    chapter_label: str | None = None


@dataclass(frozen=True, slots=True)
class RealCorpusEvalSpec:
    corpus_path: Path
    cases: tuple[RealCorpusEvalCase, ...]


def load_real_corpus_eval_spec(spec_path: Path) -> RealCorpusEvalSpec:
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Real corpus eval spec must be a JSON object.")
    corpus_path_value = payload.get("corpus_path")
    if not isinstance(corpus_path_value, str) or not corpus_path_value.strip():
        raise ValueError("Real corpus eval spec requires corpus_path.")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Real corpus eval spec requires at least one case.")

    cases: list[RealCorpusEvalCase] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("Real corpus eval case must be a JSON object.")
        if any(key in raw_case for key in ("text", "slice_text", "excerpt")):
            raise ValueError("Real corpus eval cases must not embed corpus text.")
        case_id = raw_case.get("case_id")
        line_start = raw_case.get("line_start")
        line_end = raw_case.get("line_end")
        chapter_label = raw_case.get("chapter_label")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Real corpus eval case requires case_id.")
        if not isinstance(line_start, int) or line_start < 1:
            raise ValueError("Real corpus eval case requires positive line_start.")
        if not isinstance(line_end, int) or line_end < line_start:
            raise ValueError("Real corpus eval case requires line_end >= line_start.")
        if chapter_label is not None and (
            not isinstance(chapter_label, str) or not chapter_label.strip()
        ):
            raise ValueError("Real corpus eval chapter_label must be empty or a non-empty string.")
        cases.append(
            RealCorpusEvalCase(
                case_id=case_id.strip(),
                chapter_label=chapter_label.strip() if isinstance(chapter_label, str) else None,
                line_start=line_start,
                line_end=line_end,
            )
        )

    return RealCorpusEvalSpec(
        corpus_path=_resolve_corpus_path(corpus_path_value.strip()),
        cases=tuple(cases),
    )


def run_real_corpus_memory_boundary_eval(spec_path: Path) -> dict[str, object]:
    spec = load_real_corpus_eval_spec(spec_path)
    corpus_lines = spec.corpus_path.read_text(encoding="utf-8").splitlines()

    case_results: list[dict[str, object]] = []
    passed = 0
    for case in spec.cases:
        slice_text = "\n".join(corpus_lines[case.line_start - 1 : case.line_end]).strip()
        result = _run_memory_boundary_case(case, slice_text)
        case_results.append(result)
        if result["status"] == "pass":
            passed += 1

    return {
        "corpus_path": str(spec.corpus_path),
        "summary": {
            "case_count": len(spec.cases),
            "passed": passed,
            "failed": len(spec.cases) - passed,
        },
        "cases": case_results,
    }


def _resolve_corpus_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return _repo_root() / path


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "AGENTS.md").exists() and (parent / "PLAN.md").exists():
            return parent
    raise RuntimeError("Could not locate Sextant repository root.")


def _run_memory_boundary_case(case: RealCorpusEvalCase, slice_text: str) -> dict[str, object]:
    with TemporaryDirectory(prefix="sextant-real-corpus-eval-") as tmpdir:
        object_store = LocalObjectStore(Path(tmpdir) / "objects")
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            delta, job = _seed_delta(session, object_store, text=slice_text)
            MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)

            skill_run = (
                session.query(SkillRun)
                .order_by(SkillRun.created_at.desc(), SkillRun.id.desc())
                .first()
            )
            structured_output = dict(skill_run.structured_output) if skill_run is not None else {}
            thread_updates = structured_output.get("thread_updates", [])
            thread_update_count = len(thread_updates) if isinstance(thread_updates, list) else 0
            fact_count = session.query(FactAssertionRecord).count()
            memory_page_count = session.query(MemoryPage).count()
            review_item_count = session.query(ReviewItemRecord).count()
            graph_edge_count = session.query(GraphProjectionEdge).count()
            source_span_count = session.query(SourceSpan).count()
            skill_run_count = session.query(SkillRun).count()
            status = (
                "pass"
                if fact_count == 0
                and thread_update_count == 0
                and memory_page_count == 0
                and review_item_count == 0
                and graph_edge_count == 0
                and source_span_count == 1
                and skill_run_count == 1
                else "fail"
            )
            return {
                "case_id": case.case_id,
                "chapter_label": case.chapter_label,
                "line_range": [case.line_start, case.line_end],
                "slice_char_count": len(slice_text),
                "status": status,
                "source_delta_id": str(delta.id),
                "source_span_count": source_span_count,
                "fact_count": fact_count,
                "thread_update_count": thread_update_count,
                "memory_page_count": memory_page_count,
                "review_item_count": review_item_count,
                "graph_edge_count": graph_edge_count,
                "skill_run_count": skill_run_count,
                "skill_run_status": skill_run.status if skill_run is not None else None,
            }


def _seed_delta(
    session: Session,
    object_store: LocalObjectStore,
    *,
    text: str,
) -> tuple[SourceDeltaRecord, JobRecord]:
    project = Project(id=uuid4(), name="Real Corpus Eval")
    raw_text_ref = object_store.put_text("raw/real-corpus-slice.txt", text)
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Real Corpus Slice",
        ownership_status="owned",
        raw_text_ref=raw_text_ref,
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
        raw_text_ref=raw_text_ref,
    )
    delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        delta_kind="replace",
        range_start=0,
        range_end=len(text),
        base_hash=version.raw_hash,
        submitted_text_ref=object_store.put_text("accepted/real-corpus-delta.txt", text),
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"real_corpus_eval": True},
        status="memory_writeback_queued",
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="running",
        idempotency_key=f"{delta.id}:pipeline-v1",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": str(delta.id),
        },
    )
    session.add_all([project, raw_source, version, delta, job])
    session.commit()
    return delta, job
