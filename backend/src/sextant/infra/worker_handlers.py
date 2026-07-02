from __future__ import annotations

from collections.abc import Callable

from sextant.infra.agent_candidate import AgentCandidateHandler
from sextant.infra.agent_review import AgentReviewHandler
from sextant.infra.context_pack_job import BuildContextPackHandler
from sextant.infra.graph_projection import GraphProjectionRebuildHandler
from sextant.infra.memory_page_rewrite import MemoryPageRewriteHandler
from sextant.infra.memory_writeback import MemoryWritebackHandler
from sextant.infra.provider_runtime import (
    reject_implicit_local_provider_default_in_production,
    reject_local_provider_instance_in_production,
)
from sextant.infra.semantic_index_job import SemanticIndexRefreshHandler
from sextant.infra.skill_replay_eval import SkillReplayEvalHandler
from sextant.infra.source_normalization import SourceNormalizationHandler
from sextant.infra.source_pipeline import (
    AggregateEventsHandler,
    DeriveFactsHandler,
    ExtractEventsHandler,
    ExtractMentionsHandler,
    ResolveAliasesHandler,
    RunConflictPolicyHandler,
)
from sextant.infra.source_structure import SourceStructureSplitHandler
from sextant.infra.worker import JobHandler
from sextant.ports.embedding import EmbeddingClient
from sextant.ports.event_aggregation import EventAggregationAdjudicationProvider
from sextant.ports.memory_extraction import MemoryExtractionProvider
from sextant.ports.object_store import ObjectStore
from sextant.ports.pov_detection import PovDetectionProvider
from sextant.ports.story_draft import StoryDraftProvider
from sextant.skills.local_embedding import LocalEmbeddingProvider
from sextant.skills.local_event_aggregation import LocalEventAggregationProvider
from sextant.skills.local_memory_extractor import LocalMemoryExtractionProvider
from sextant.skills.local_pov_detection import LocalPovDetectionProvider


def build_worker_handlers(
    object_store: ObjectStore,
    story_draft_provider: StoryDraftProvider,
    pov_detection_provider: PovDetectionProvider | None = None,
    *,
    event_aggregation_provider: EventAggregationAdjudicationProvider | None = None,
    memory_extraction_provider: MemoryExtractionProvider | None = None,
    embedding_provider: EmbeddingClient | None = None,
) -> dict[str, JobHandler]:
    reject_local_provider_instance_in_production("story_draft_provider", story_draft_provider)
    resolved_pov_detection_provider = _resolve_provider(
        "pov_detection_provider",
        pov_detection_provider,
        LocalPovDetectionProvider,
    )
    resolved_event_aggregation_provider = _resolve_provider(
        "event_aggregation_provider",
        event_aggregation_provider,
        LocalEventAggregationProvider,
    )
    resolved_memory_extraction_provider = _resolve_provider(
        "memory_extraction_provider",
        memory_extraction_provider,
        LocalMemoryExtractionProvider,
    )
    resolved_embedding_provider = _resolve_provider(
        "embedding_provider",
        embedding_provider,
        LocalEmbeddingProvider,
    )
    return {
        "normalize_source": SourceNormalizationHandler(object_store),
        "split_structure": SourceStructureSplitHandler(object_store),
        "extract_mentions": ExtractMentionsHandler(object_store),
        "resolve_aliases": ResolveAliasesHandler(resolved_pov_detection_provider, object_store),
        "extract_events": ExtractEventsHandler(object_store),
        "aggregate_events": AggregateEventsHandler(resolved_event_aggregation_provider),
        "derive_facts": DeriveFactsHandler(),
        "run_conflict_policy": RunConflictPolicyHandler(),
        "run_memory_writeback": MemoryWritebackHandler(
            object_store,
            resolved_memory_extraction_provider,
        ),
        "refresh_semantic_index": SemanticIndexRefreshHandler(resolved_embedding_provider),
        "rewrite_memory_page": MemoryPageRewriteHandler(),
        "rebuild_graph_projection": GraphProjectionRebuildHandler(),
        "build_context_pack": BuildContextPackHandler(),
        "run_agent_candidate": AgentCandidateHandler(
            object_store,
            story_draft_provider,
        ),
        "run_agent_review": AgentReviewHandler(object_store),
        "run_skill_replay_eval": SkillReplayEvalHandler(),
    }


def _resolve_provider[ProviderT](
    parameter_name: str,
    provider: ProviderT | None,
    local_factory: Callable[[], ProviderT],
) -> ProviderT:
    if provider is None:
        reject_implicit_local_provider_default_in_production(parameter_name)
        provider = local_factory()
    reject_local_provider_instance_in_production(parameter_name, provider)
    return provider
