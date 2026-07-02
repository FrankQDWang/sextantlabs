from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from sextant.infra.db.models import (
    AuditEvent,
    JobRecord,
    RawSource,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
    StoryChapter,
    StoryScene,
)
from sextant.infra.worker import TerminalJobError
from sextant.ports.object_store import ObjectStore

PIPELINE_VERSION = "pipeline-v1"
MENTION_EXTRACTOR_VERSION = "mention-extractor-v1"
SOURCE_SPAN_MAX_CHARS = 1200
SOURCE_SPAN_MIN_BOUNDARY_CHARS = 300
EXTRACT_MENTION_JOB_BATCH_SIZE = 50
EXTRACT_MENTION_JOB_BATCH_SIZE_LIMIT = 500
SCENE_TIME_METADATA_PATTERN = re.compile(
    r"^\s*(?:Time|Story Time|时间)\s*[:：]\s*(?P<value>.+)$", re.IGNORECASE
)
SCENE_TONE_METADATA_PATTERN = re.compile(
    r"^\s*(?:Tone|Emotional Tone|情绪|基调)\s*[:：]\s*(?P<value>.+)$", re.IGNORECASE
)
SCENE_FUNCTION_METADATA_PATTERN = re.compile(
    r"^\s*(?:Function|Scene Function|场景功能|功能)\s*[:：]\s*(?P<value>.+)$",
    re.IGNORECASE,
)
ENGLISH_DIALOGUE_LINE_SPEAKER_PATTERN = re.compile(
    r"^\s*(?:"
    r"[A-Z][A-Za-z0-9'-]*(?:\s+[A-Z][A-Za-z0-9'-]*){0,2}\s+"
    r"(?i:said|says|asked|asks|whispered|replied|answered|shouted|warned|called|murmured)\b"
    r"|[\"“‘].*[\"”’]\s*,?\s*"
    r"[A-Z][A-Za-z0-9'-]*(?:\s+[A-Z][A-Za-z0-9'-]*){0,2}\s+"
    r"(?i:said|says|asked|asks|whispered|replied|answered|shouted|warned|called|murmured)\b"
    r")"
)
CHINESE_DIALOGUE_LINE_SPEAKER_PATTERN = re.compile(
    r"(?:"
    r"^\s*(?:[\u4e00-\u9fff·]{2,8}?|[他她])\s*(?:低声说|回答|喊道|警告|提醒|说|问)"
    r"|[\"“‘].*[\"”’]\s*[,，]?\s*"
    r"(?:[\u4e00-\u9fff·]{2,8}?|[他她])\s*(?:低声说|回答|喊道|警告|提醒|说|问)"
    r")"
)
ENGLISH_INLINE_DIALOGUE_SEGMENT_PATTERN = re.compile(
    r"(?:"
    r"[A-Z][A-Za-z0-9'-]*(?:\s+[A-Z][A-Za-z0-9'-]*){0,2}\s+"
    r"(?i:said|says|asked|asks|whispered|replied|answered|shouted|warned|called|murmured)\b"
    r"\s*[:,]?\s*[\"“‘][^\"”’]{1,240}[\"”’]"
    r"|[\"“‘][^\"”’]{1,240}[\"”’]\s*,?\s*"
    r"[A-Z][A-Za-z0-9'-]*(?:\s+[A-Z][A-Za-z0-9'-]*){0,2}\s+"
    r"(?i:said|says|asked|asks|whispered|replied|answered|shouted|warned|called|murmured)\b"
    r"[.!?]?"
    r")"
)
CHINESE_INLINE_DIALOGUE_SEGMENT_PATTERN = re.compile(
    r"(?:"
    r"(?:[\u4e00-\u9fff·]{2,8}?|[他她])\s*(?:低声说|回答|喊道|警告|提醒|说|问)"
    r"\s*[,，:：]?\s*[\"“‘][^\"”’\n]{1,160}[\"”’]\s*[。！？!?]?"
    r"|[^\"“‘\n]{0,120}?[\"“‘][^\"”’\n]{1,160}[\"”’]\s*[,，]?\s*"
    r"(?:[\u4e00-\u9fff·]{2,8}?|[他她])\s*(?:低声说|回答|喊道|警告|提醒|说|问)\s*[。！？!?]?"
    r")"
)


@dataclass(frozen=True, slots=True)
class StructureSplitResult:
    chapter_ids: list[UUID]
    scene_ids: list[UUID]
    created: bool


@dataclass(frozen=True, slots=True)
class SourceSpanPipelineScheduling:
    source_span_ids: list[UUID]
    enqueued_extract_job_count: int
    deferred_extract_job_count: int


class SourceStructureSplitHandler:
    def __init__(self, object_store: ObjectStore) -> None:
        self._object_store = object_store

    def __call__(self, session: Session, job: JobRecord) -> None:
        view_id = _payload_uuid(job, "processed_view_id")
        parser_version = _payload_text(job, "parser_version")
        view = session.get(SourceProcessedView, view_id)
        if view is None:
            raise TerminalJobError("ProcessedMarkdownView was not found for structure split.")
        markdown = self._object_store.get_text(view.markdown_ref)
        if not markdown.strip():
            raise TerminalJobError("ProcessedMarkdownView text is empty for structure split.")

        result = split_structure(
            session,
            view=view,
            markdown=markdown,
            chapter_title=_chapter_title(job),
        )
        scheduling = _ensure_scene_spans_and_pipeline_jobs(
            session,
            job=job,
            view=view,
            markdown=markdown,
            scene_ids=result.scene_ids,
        )
        session.add(
            AuditEvent(
                id=uuid4(),
                project_id=job.project_id,
                request_id=f"job:{job.id}",
                actor_id=None,
                event_type="source.structure_split",
                subject_ref={"type": "source_processed_view", "id": str(view.id)},
                decision={
                    "processed_view_id": str(view.id),
                    "parser_version": parser_version,
                    "chapter_ids": [str(chapter_id) for chapter_id in result.chapter_ids],
                    "scene_ids": [str(scene_id) for scene_id in result.scene_ids],
                    "source_span_ids": [str(span_id) for span_id in scheduling.source_span_ids],
                    "source_span_count": len(scheduling.source_span_ids),
                    "extract_mentions_jobs_enqueued": scheduling.enqueued_extract_job_count,
                    "extract_mentions_jobs_deferred": scheduling.deferred_extract_job_count,
                    "chapter_count": len(result.chapter_ids),
                    "scene_count": len(result.scene_ids),
                    "created": result.created,
                },
            )
        )
        session.flush()


def split_structure(
    session: Session,
    *,
    view: SourceProcessedView,
    markdown: str,
    chapter_title: str,
) -> StructureSplitResult:
    existing_chapters = list(
        session.scalars(select(StoryChapter).where(StoryChapter.view_id == view.id))
    )
    if existing_chapters:
        existing_scene_ids = [
            scene.id
            for chapter in existing_chapters
            for scene in session.scalars(
                select(StoryScene).where(StoryScene.chapter_id == chapter.id)
            )
        ]
        return StructureSplitResult(
            chapter_ids=[chapter.id for chapter in existing_chapters],
            scene_ids=existing_scene_ids,
            created=False,
        )

    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title=chapter_title,
        start_offset=0,
        end_offset=len(markdown),
        summary=None,
    )
    session.add(chapter)
    session.flush()

    scene_ids: list[UUID] = []
    for scene_index, (start_offset, end_offset) in enumerate(_scene_ranges(markdown)):
        scene_metadata = _scene_metadata_fields(markdown[start_offset:end_offset])
        scene = StoryScene(
            id=uuid4(),
            chapter_id=chapter.id,
            scene_index=scene_index,
            location_entity_id=None,
            pov_character_id=None,
            pov_mode=None,
            pov_confidence=None,
            pov_evidence_span_ids=[],
            pov_uncertainty_reason=None,
            story_time=scene_metadata.get("story_time"),
            emotional_tone=scene_metadata.get("emotional_tone"),
            scene_summary=None,
            scene_function=scene_metadata.get("scene_function"),
            start_offset=start_offset,
            end_offset=end_offset,
        )
        session.add(scene)
        scene_ids.append(scene.id)
    session.flush()
    return StructureSplitResult(chapter_ids=[chapter.id], scene_ids=scene_ids, created=True)


def _ensure_scene_spans_and_pipeline_jobs(
    session: Session,
    *,
    job: JobRecord,
    view: SourceProcessedView,
    markdown: str,
    scene_ids: list[UUID],
) -> SourceSpanPipelineScheduling:
    version = session.get(SourceVersion, view.version_id)
    if version is None:
        raise TerminalJobError("SourceVersion was not found for structure split.")
    raw_source = session.get(RawSource, version.source_id)
    if raw_source is None or raw_source.project_id != job.project_id:
        raise TerminalJobError("ProcessedMarkdownView does not belong to the job project.")

    source_spans: list[SourceSpan] = []
    scenes = list(
        session.scalars(
            select(StoryScene)
            .where(StoryScene.id.in_(scene_ids))
            .order_by(StoryScene.scene_index, StoryScene.id)
        )
    )
    for scene in scenes:
        existing_spans = list(
            session.scalars(
                select(SourceSpan)
                .where(SourceSpan.view_id == view.id)
                .where(SourceSpan.scene_id == scene.id)
                .order_by(SourceSpan.start_offset, SourceSpan.id)
            )
        )
        if existing_spans:
            for span in existing_spans:
                source_spans.append(span)
            continue
        for start_offset, end_offset in _source_span_ranges(
            markdown,
            scene.start_offset,
            scene.end_offset,
        ):
            span = SourceSpan(
                id=uuid4(),
                source_id=raw_source.id,
                version_id=version.id,
                view_id=view.id,
                chapter_id=scene.chapter_id,
                scene_id=scene.id,
                start_offset=start_offset,
                end_offset=end_offset,
                raw_start_offset=start_offset,
                raw_end_offset=end_offset,
                text_preview=markdown[start_offset:end_offset][:500],
                speaker_entity_id=None,
                narration_layer="narrator",
            )
            session.add(span)
            session.flush()
            source_spans.append(span)
    enqueued_count, deferred_count = _enqueue_extract_mentions_jobs(
        session,
        job=job,
        view=view,
        source_spans=source_spans,
    )
    return SourceSpanPipelineScheduling(
        source_span_ids=[span.id for span in source_spans],
        enqueued_extract_job_count=enqueued_count,
        deferred_extract_job_count=deferred_count,
    )


def _source_span_ranges(markdown: str, start_offset: int, end_offset: int) -> list[tuple[int, int]]:
    dialogue_line_ranges = _dialogue_line_span_ranges(markdown, start_offset, end_offset)
    if dialogue_line_ranges is not None:
        return dialogue_line_ranges

    dialogue_inline_ranges = _dialogue_inline_span_ranges(markdown, start_offset, end_offset)
    if dialogue_inline_ranges is not None:
        return dialogue_inline_ranges

    ranges: list[tuple[int, int]] = []
    cursor = start_offset
    while cursor < end_offset:
        while cursor < end_offset and markdown[cursor].isspace():
            cursor += 1
        if cursor >= end_offset:
            break
        if end_offset - cursor <= SOURCE_SPAN_MAX_CHARS:
            ranges.append((cursor, end_offset))
            break

        limit = cursor + SOURCE_SPAN_MAX_CHARS
        split_at = _best_span_boundary(markdown, cursor, limit)
        if split_at <= cursor:
            split_at = limit

        split_end = split_at
        while split_end > cursor and markdown[split_end - 1].isspace():
            split_end -= 1
        if split_end <= cursor:
            split_end = split_at
        ranges.append((cursor, split_end))
        cursor = split_at

    return ranges or [(start_offset, end_offset)]


def _dialogue_line_span_ranges(
    markdown: str,
    start_offset: int,
    end_offset: int,
) -> list[tuple[int, int]] | None:
    ranges = list(_non_empty_line_ranges(markdown, start_offset, end_offset))
    if len(ranges) < 2:
        return None
    if not all(_looks_like_dialogue_attribution_line(markdown[start:end]) for start, end in ranges):
        return None
    return ranges


def _non_empty_line_ranges(
    markdown: str,
    start_offset: int,
    end_offset: int,
) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    cursor = start_offset
    while cursor < end_offset:
        line_end = markdown.find("\n", cursor, end_offset)
        if line_end == -1:
            line_end = end_offset
        content_start = cursor
        content_end = line_end
        while content_start < content_end and markdown[content_start].isspace():
            content_start += 1
        while content_end > content_start and markdown[content_end - 1].isspace():
            content_end -= 1
        if content_end > content_start:
            ranges.append((content_start, content_end))
        cursor = line_end + 1
    return ranges


def _looks_like_dialogue_attribution_line(text: str) -> bool:
    if '"' not in text and "“" not in text and "‘" not in text:
        return False
    return bool(
        ENGLISH_DIALOGUE_LINE_SPEAKER_PATTERN.search(text)
        or CHINESE_DIALOGUE_LINE_SPEAKER_PATTERN.search(text)
    )


def _dialogue_inline_span_ranges(
    markdown: str,
    start_offset: int,
    end_offset: int,
) -> list[tuple[int, int]] | None:
    text = markdown[start_offset:end_offset]
    matches = list(ENGLISH_INLINE_DIALOGUE_SEGMENT_PATTERN.finditer(text))
    if len(matches) < 2:
        matches = list(CHINESE_INLINE_DIALOGUE_SEGMENT_PATTERN.finditer(text))
    if len(matches) < 2:
        return None

    ranges: list[tuple[int, int]] = []
    cursor = 0
    for match in matches:
        segment_start = match.start()
        segment_end = match.end()
        while segment_start < segment_end and text[segment_start].isspace():
            segment_start += 1
        while segment_end > segment_start and text[segment_end - 1].isspace():
            segment_end -= 1
        if text[cursor:segment_start].strip():
            separator_end = _inline_dialogue_separator_end(text, cursor, segment_start)
            if separator_end is None or not ranges:
                return None
            previous_start, _previous_end = ranges[-1]
            ranges[-1] = (previous_start, start_offset + separator_end)
        if segment_end <= segment_start:
            return None
        ranges.append((start_offset + segment_start, start_offset + segment_end))
        cursor = match.end()
    if text[cursor:].strip():
        return None
    return ranges


def _inline_dialogue_separator_end(text: str, start_offset: int, end_offset: int) -> int | None:
    separator = text[start_offset:end_offset]
    stripped = separator.strip()
    if stripped not in {",", ";", "；", "—"}:
        return None
    return start_offset + len(separator.rstrip())


def _best_span_boundary(markdown: str, cursor: int, limit: int) -> int:
    window = markdown[cursor:limit]
    best = -1
    for boundary in ("\n", "。", "！", "？", ".", "!", "?"):
        position = window.rfind(boundary)
        if position > best:
            best = position
    if best >= SOURCE_SPAN_MIN_BOUNDARY_CHARS:
        return cursor + best + 1
    return limit


def _enqueue_extract_mentions_jobs(
    session: Session,
    *,
    job: JobRecord,
    view: SourceProcessedView,
    source_spans: list[SourceSpan],
) -> tuple[int, int]:
    batch_size = _extract_batch_size(job)
    unscheduled_spans = [
        span for span in source_spans if not _extract_mentions_job_exists(session, job, span)
    ]
    batch = unscheduled_spans[:batch_size]
    for span in batch:
        _enqueue_extract_mentions_job(session, job, view, span)

    deferred_spans = unscheduled_spans[batch_size:]
    if deferred_spans:
        _enqueue_split_structure_continuation_job(
            session,
            job=job,
            view=view,
            batch_size=batch_size,
            first_deferred_span=deferred_spans[0],
            deferred_count=len(deferred_spans),
        )
    return len(batch), len(deferred_spans)


def _enqueue_extract_mentions_job(
    session: Session,
    job: JobRecord,
    view: SourceProcessedView,
    span: SourceSpan,
) -> None:
    if _extract_mentions_job_exists(session, job, span):
        return
    session.add(
        JobRecord(
            id=uuid4(),
            project_id=job.project_id,
            job_type="extract_mentions",
            status="queued",
            idempotency_key=f"{span.id}:{MENTION_EXTRACTOR_VERSION}",
            payload={
                "step": "extract_mentions",
                "pipeline_version": PIPELINE_VERSION,
                "source_span_id": str(span.id),
                "extractor_version": MENTION_EXTRACTOR_VERSION,
                "trigger": "split_structure",
                "processed_view_id": str(view.id),
            },
        )
    )


def _extract_mentions_job_exists(session: Session, job: JobRecord, span: SourceSpan) -> bool:
    return (
        session.scalars(
            select(JobRecord)
            .where(JobRecord.project_id == job.project_id)
            .where(JobRecord.job_type == "extract_mentions")
            .where(JobRecord.idempotency_key == f"{span.id}:{MENTION_EXTRACTOR_VERSION}")
        ).first()
        is not None
    )


def _enqueue_split_structure_continuation_job(
    session: Session,
    *,
    job: JobRecord,
    view: SourceProcessedView,
    batch_size: int,
    first_deferred_span: SourceSpan,
    deferred_count: int,
) -> None:
    parser_version = _payload_text(job, "parser_version")
    idempotency_key = (
        f"{view.id}:{parser_version}:{MENTION_EXTRACTOR_VERSION}:continue:{first_deferred_span.id}"
    )
    existing = session.scalars(
        select(JobRecord)
        .where(JobRecord.project_id == job.project_id)
        .where(JobRecord.job_type == "split_structure")
        .where(JobRecord.idempotency_key == idempotency_key)
    ).first()
    if existing is not None:
        return
    session.add(
        JobRecord(
            id=uuid4(),
            project_id=job.project_id,
            job_type="split_structure",
            status="queued",
            idempotency_key=idempotency_key,
            payload={
                "step": "split_structure",
                "pipeline_version": PIPELINE_VERSION,
                "processed_view_id": str(view.id),
                "parser_version": parser_version,
                "chapter_title": _chapter_title(job),
                "trigger": "split_structure_backpressure",
                "source_version_id": str(view.version_id),
                "extract_batch_size": batch_size,
                "continues_job_id": str(job.id),
                "first_deferred_source_span_id": str(first_deferred_span.id),
                "deferred_extract_mentions_count": deferred_count,
            },
        )
    )


def _extract_batch_size(job: JobRecord) -> int:
    value = job.payload.get("extract_batch_size")
    if value is None:
        return EXTRACT_MENTION_JOB_BATCH_SIZE
    if not isinstance(value, int) or isinstance(value, bool):
        raise TerminalJobError("extract_batch_size must be a positive integer.")
    if value <= 0 or value > EXTRACT_MENTION_JOB_BATCH_SIZE_LIMIT:
        raise TerminalJobError(
            f"extract_batch_size must be between 1 and {EXTRACT_MENTION_JOB_BATCH_SIZE_LIMIT}."
        )
    return value


def _scene_ranges(markdown: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for match in re.finditer(r"\S[\s\S]*?(?=(?:\n\s*\n)|\Z)", markdown):
        start = match.start()
        end = start + len(match.group(0).rstrip())
        if end > start:
            ranges.append((start, end))
    if not ranges and markdown.strip():
        start = len(markdown) - len(markdown.lstrip())
        end = len(markdown.rstrip())
        ranges.append((start, end))
    return ranges


def _scene_metadata_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if match := SCENE_TIME_METADATA_PATTERN.match(line):
            fields["story_time"] = _metadata_value(match.group("value"))
            continue
        if match := SCENE_TONE_METADATA_PATTERN.match(line):
            fields["emotional_tone"] = _metadata_value(match.group("value"))
            continue
        if match := SCENE_FUNCTION_METADATA_PATTERN.match(line):
            fields["scene_function"] = _metadata_value(match.group("value"))
            continue
        break
    return fields


def _metadata_value(value: str) -> str:
    return value.strip()[:200]


def _payload_uuid(job: JobRecord, key: str) -> UUID:
    value = job.payload.get(key)
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise TerminalJobError(f"job payload requires {key}") from exc


def _payload_text(job: JobRecord, key: str) -> str:
    value = job.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TerminalJobError(f"job payload requires {key}")
    return value.strip()


def _chapter_title(job: JobRecord) -> str:
    value = job.payload.get("chapter_title")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "Chapter 1"
