"""Focused tests for the runtime LLM-facing retrieval search service."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rp.models.dsl import Domain
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import (
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    RetrievalSearchResult,
)
from rp.models.retrieval_runtime_contracts import RuntimeRetrievalSearchInput
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterial
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialVisibility
from rp.services.runtime_retrieval_search_service import RuntimeRetrievalSearchService


def _identity() -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id="story-runtime-search",
        session_id="session-runtime-search",
        branch_head_id="branch-runtime-search",
        turn_id="turn-runtime-search",
        runtime_profile_snapshot_id="profile-runtime-search",
    )


def _material(
    *,
    material_id: str,
    short_id: str,
    search_kind: str,
    title: str,
    text: str,
    rank: int,
    summary: str | None = None,
    summary_source: str | None = None,
) -> RuntimeWorkspaceMaterial:
    return RuntimeWorkspaceMaterial(
        material_id=material_id,
        material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
        identity=_identity(),
        domain=Domain.CHAPTER.value,
        domain_path=f"chapter.test.{short_id.lower()}",
        short_id=short_id,
        payload={
            "title": title,
            "text": text,
            "excerpt": text,
            "summary": summary,
            "summary_source": summary_source,
            "search_kind": search_kind,
            "rank": rank,
            "metadata": {
                "section_title": "关系",
                "asset_id": "asset-hidden",
                "chunk_id": "chunk-hidden",
                "score": 99,
            },
        },
        visibility=RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
        created_by="test",
    )


class _StubCardService:
    def __init__(self) -> None:
        self.recall_inputs: list[MemorySearchRecallInput] = []
        self.archival_inputs: list[MemorySearchArchivalInput] = []

    async def search_recall_to_cards(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        input_model: MemorySearchRecallInput,
        actor: str,
        attempt_index: int = 1,
    ) -> tuple[RetrievalSearchResult, list[RuntimeWorkspaceMaterial], None]:
        _ = identity, actor, attempt_index
        self.recall_inputs.append(input_model)
        return (
            RetrievalSearchResult(
                query=input_model.query, hits=[], warnings=["recall warn"]
            ),
            [
                _material(
                    material_id="recall-card-1",
                    short_id="R1",
                    search_kind="recall",
                    title="回忆：林鸢",
                    text="林鸢在第一章救下夜紫林。",
                    rank=1,
                )
            ],
            None,
        )

    async def search_archival_to_cards(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        input_model: MemorySearchArchivalInput,
        actor: str,
        attempt_index: int = 1,
    ) -> tuple[RetrievalSearchResult, list[RuntimeWorkspaceMaterial], None]:
        _ = identity, actor, attempt_index
        self.archival_inputs.append(input_model)
        return (
            RetrievalSearchResult(
                query=input_model.query, hits=[], warnings=["archival warn"]
            ),
            [
                _material(
                    material_id="archival-card-1",
                    short_id="R2",
                    search_kind="archival",
                    title="设定：林鸢与夜紫林",
                    text="林鸢与夜紫林是互相试探但彼此信任的同盟关系。",
                    rank=1,
                    summary="两人关系的已沉淀设定摘要。",
                    summary_source="entry_summary",
                )
            ],
            None,
        )


@pytest.mark.parametrize(
    "backend_control",
    [
        {"search_kind": "archival"},
        {"top_k": 50},
        {"filters": {"source_families": ["foundation_entry"]}},
        {"rerank": True},
        {"rerank_top_n": 10},
        {"route_weights": {"keyword": 2.0, "semantic": 1.0}},
        {"candidate_top_k": 40},
    ],
)
def test_runtime_retrieval_search_input_rejects_backend_controls(
    backend_control: dict[str, object],
):
    payload = {
        "query": "林鸢和夜紫林的关系怎么样",
        **backend_control,
    }
    with pytest.raises(ValidationError):
        RuntimeRetrievalSearchInput.model_validate(payload)


def test_runtime_retrieval_search_input_normalizes_hints():
    payload = RuntimeRetrievalSearchInput.model_validate(
        {
            "query": " 林鸢和夜紫林的关系怎么样 ",
            "mode": "entity_relation",
            "lexical_anchors": [" 林鸢 ", "夜紫林", "林鸢"],
            "semantic_predicates": ["关系", "关系", "  "],
        }
    )
    assert payload.query == "林鸢和夜紫林的关系怎么样"
    assert payload.lexical_anchors == ["林鸢", "夜紫林"]
    assert payload.semantic_predicates == ["关系"]


@pytest.mark.asyncio
async def test_runtime_retrieval_search_service_merges_sources_and_cleans_output():
    card_service = _StubCardService()
    service = RuntimeRetrievalSearchService(
        runtime_retrieval_card_service=card_service,
        final_top_k=5,
    )

    execution = await service.search_for_writer(
        identity=_identity(),
        input_model=RuntimeRetrievalSearchInput(
            query="林鸢和夜紫林的关系怎么样",
            mode="entity_relation",
            lexical_anchors=["林鸢", "夜紫林"],
            semantic_predicates=["关系"],
        ),
        actor="writer.retrieval",
    )

    assert (
        card_service.recall_inputs[0].query
        == "林鸢和夜紫林的关系怎么样 林鸢 夜紫林 关系"
    )
    assert (
        card_service.archival_inputs[0].query
        == "林鸢和夜紫林的关系怎么样 林鸢 夜紫林 关系"
    )
    assert [item.result_id for item in execution.output.results] == ["R1", "R2"]
    assert execution.output.results[0].summary is None
    assert execution.output.results[0].excerpt == "林鸢在第一章救下夜紫林。"
    assert execution.output.results[1].summary == "两人关系的已沉淀设定摘要。"
    assert execution.output.results[1].excerpt is None
    serialized = execution.output.model_dump(mode="json", exclude_none=True)
    result_keys = set(serialized["results"][0].keys())
    assert result_keys <= {
        "result_id",
        "title",
        "summary",
        "excerpt",
        "text",
        "section",
    }
    assert "score" not in serialized["results"][0]
    assert "metadata" not in serialized["results"][0]
    assert "search_kind" not in serialized["results"][0]
    assert execution.output.warnings == ["recall warn", "archival warn"]
    assert [material.material_id for material in execution.materials] == [
        "recall-card-1",
        "archival-card-1",
    ]
