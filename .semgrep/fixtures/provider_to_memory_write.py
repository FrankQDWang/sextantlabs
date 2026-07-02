from sextant.infra.db.models import FactAssertionRecord


class BadStoryDraftProvider:
    def draft(self, project_id):
        return FactAssertionRecord(
            id="fact-1",
            project_id=project_id,
            subject_ref={"type": "character", "id": "mira"},
            predicate="owns",
            object_ref={"type": "object", "id": "lantern-map"},
            fact_status="proposed",
            evidence_span_ids=["span-1"],
            confidence=0.9,
            source_scope="model_suggestion",
        )
