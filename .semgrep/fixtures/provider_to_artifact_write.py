from sextant.infra.db.models import GraphProjectionEdge, SourceDeltaRecord


class BadArtifactProvider:
    def draft(self, project_id):
        delta = SourceDeltaRecord(
            id="delta-1",
            project_id=project_id,
            source_id="source-1",
            kind="insert",
            submitted_text_ref={"uri": "object://candidate"},
            base_version_id="version-1",
            new_version_id="version-2",
            status="committed",
        )
        edge = GraphProjectionEdge(
            id="edge-1",
            project_id=project_id,
            run_id="run-1",
            source_ref={"type": "model_output", "id": "candidate-1"},
            subject_ref={"type": "character", "id": "mira"},
            relation="owns",
            target_ref={"type": "object", "id": "lantern-map"},
            edge_status="canon",
            evidence_refs=[],
        )
        return delta, edge
