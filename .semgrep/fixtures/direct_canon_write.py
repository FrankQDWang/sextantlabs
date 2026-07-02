from sextant.infra.db.models import FactAssertionRecord


def bad_direct_write(project_id):
    return FactAssertionRecord(
        id="fact-1",
        project_id=project_id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        evidence_span_ids=["span-1"],
        confidence=1.0,
        source_scope="model_suggestion",
    )
