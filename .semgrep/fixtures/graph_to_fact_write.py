from sextant.infra.db.models import FactAssertionRecord, GraphProjectionEdge


def bad_graph_to_fact(project_id, run_id):
    edge = GraphProjectionEdge(
        id="edge-1",
        project_id=project_id,
        run_id=run_id,
        source_ref={"type": "fact_assertion", "id": "fact-1"},
        subject_ref={"type": "character", "id": "mira"},
        relation="owns",
        target_ref={"type": "object", "id": "lantern-map"},
        edge_status="canon",
        evidence_refs=[{"type": "source_span", "id": "span-1"}],
    )
    fact = FactAssertionRecord(
        id="fact-2",
        project_id=project_id,
        subject_ref=edge.subject_ref,
        predicate=edge.relation,
        object_ref=edge.target_ref,
        fact_status="proposed",
        evidence_span_ids=["span-1"],
        confidence=1.0,
        source_scope="user_draft",
    )
    return edge, fact
