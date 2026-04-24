"""Tests for hosted reranker backend and cross-encoder reranker behavior."""

from __future__ import annotations

from datetime import datetime, timezone

from models.model_registry import ModelRegistryEntry
from models.provider_registry import ProviderRegistryEntry
from models.chat import ChatMessage
from rp.models.dsl import Domain
from rp.models.memory_crud import RetrievalHit, RetrievalQuery, RetrievalSearchResult, RetrievalTrace
from rp.retrieval.reranker import CrossEncoderReranker, LLMReranker
from rp.retrieval.reranker_backends import (
    HostedRerankerBackend,
    LocalCrossEncoderBackend,
    RerankerBackendChain,
)
from rp.retrieval.reranker_resolver import HostedRerankerResolver, LocalCrossEncoderResolver
import pytest


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _FakeModelRegistryService:
    def __init__(self, entries: list[ModelRegistryEntry]) -> None:
        self._entries = {entry.id: entry for entry in entries}

    def get_entry(self, model_id: str):
        return self._entries.get(model_id)

    def list_entries(self, *, provider_id: str | None = None):
        entries = list(self._entries.values())
        if provider_id is not None:
            entries = [entry for entry in entries if entry.provider_id == provider_id]
        return entries


class _FakeProviderRegistryService:
    def __init__(self, entries: list[ProviderRegistryEntry]) -> None:
        self._entries = {entry.id: entry for entry in entries}

    def get_entry(self, provider_id: str):
        return self._entries.get(provider_id)

    def list_entries(self):
        return list(self._entries.values())


class _FakeLiteLLMService:
    def __init__(self, response: dict | None = None, *, error: Exception | None = None) -> None:
        self._response = response or {"results": []}
        self._error = error
        self.calls: list[dict] = []

    def rerank(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class _FakeStoryLlmGateway:
    def __init__(self, response_text: str | None = None, *, error: Exception | None = None) -> None:
        self._response_text = response_text or '{"ordered_hit_ids":["chunk-b","chunk-a"]}'
        self._error = error
        self.calls: list[dict] = []

    async def complete_text(self, **kwargs) -> str:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response_text


def _provider_entry() -> ProviderRegistryEntry:
    return ProviderRegistryEntry(
        id="provider-rerank",
        name="Cohere Rerank",
        type="cohere",
        api_key="secret",
        api_url="https://api.cohere.com/v2/rerank",
        is_enabled=True,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )


def _openai_provider_entry() -> ProviderRegistryEntry:
    return ProviderRegistryEntry(
        id="provider-openai-rerank",
        name="OpenAI Compatible Rerank",
        type="openai",
        api_key="secret",
        api_url="https://example.com/v1/chat/completions",
        is_enabled=True,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )


def _local_provider_entry() -> ProviderRegistryEntry:
    return ProviderRegistryEntry(
        id="provider-local-rerank",
        name="Local Rerank",
        type="local",
        api_key="unused",
        api_url="local://cross-encoder",
        is_enabled=True,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )


def _model_entry(*, capabilities: list[str] | None = None) -> ModelRegistryEntry:
    return ModelRegistryEntry(
        id="model-rerank",
        provider_id="provider-rerank",
        model_name="rerank-v4.0",
        display_name="Rerank V4",
        capabilities=capabilities or ["rerank"],
        is_enabled=True,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )


def _local_model_entry(*, capabilities: list[str] | None = None) -> ModelRegistryEntry:
    return ModelRegistryEntry(
        id="model-local-rerank",
        provider_id="provider-local-rerank",
        model_name="local-cross-encoder",
        display_name="Local Cross Encoder",
        capabilities=capabilities or ["cross_encoder_rerank"],
        is_enabled=True,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )


def _openai_rerank_model_entry(*, capabilities: list[str] | None = None) -> ModelRegistryEntry:
    return ModelRegistryEntry(
        id="model-openai-rerank",
        provider_id="provider-openai-rerank",
        model_name="Qwen/Qwen3-VL-Reranker-8B",
        display_name="OpenAI Compatible Rerank",
        capabilities=capabilities or ["rerank"],
        is_enabled=True,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )


def _non_rerank_model_entry() -> ModelRegistryEntry:
    return ModelRegistryEntry(
        id="model-text-only",
        provider_id="provider-rerank",
        model_name="text-model-v1",
        display_name="Text Model",
        capabilities=["text"],
        is_enabled=True,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )


def _retrieval_result() -> RetrievalSearchResult:
    return RetrievalSearchResult(
        query="moon gate ritual",
        hits=[
            RetrievalHit(
                hit_id="chunk-a",
                query_id="rq-rerank",
                layer="archival",
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.misc",
                excerpt_text="A generic rule.",
                score=0.61,
                rank=1,
                metadata={
                    "asset_id": "asset-a",
                    "title": "Generic Rule",
                    "document_title": "Worldbook",
                    "document_summary": "Worldbook summary",
                    "context_header": "Worldbook :: Generic Rule :: foundation.world.misc",
                    "contextual_text": "Context: Worldbook :: Generic Rule :: foundation.world.misc\nSummary: Worldbook summary\nA generic rule.",
                },
            ),
            RetrievalHit(
                hit_id="chunk-b",
                query_id="rq-rerank",
                layer="archival",
                domain=Domain.WORLD_RULE,
                domain_path="foundation.world.moon_gate",
                excerpt_text="Moon gate rituals must be witnessed at dawn.",
                score=0.58,
                rank=2,
                metadata={
                    "asset_id": "asset-b",
                    "title": "Moon Gate Ritual",
                    "document_title": "Worldbook",
                    "document_summary": "Worldbook summary",
                    "context_header": "Worldbook :: Moon Gate Ritual :: foundation.world.moon_gate",
                    "contextual_text": "Context: Worldbook :: Moon Gate Ritual :: foundation.world.moon_gate\nSummary: Worldbook summary\nMoon gate rituals must be witnessed at dawn.",
                },
            ),
        ],
        trace=RetrievalTrace(
            trace_id="trace-rerank",
            query_id="rq-rerank",
            route="retrieval.hybrid.rrf",
            result_kind="chunk",
            retriever_routes=["retrieval.keyword.lexical", "retrieval.semantic.python"],
            pipeline_stages=["retrieve", "fusion"],
            candidate_count=2,
            returned_count=2,
            timings={"fusion_ms": 1.0},
        ),
    )


def test_hosted_reranker_backend_resolves_capability_model_and_calls_litellm():
    litellm_service = _FakeLiteLLMService(
        response={"results": [{"index": 1, "relevance_score": 0.91}, {"index": 0, "relevance_score": 0.42}]}
    )
    backend = HostedRerankerBackend(
        litellm_service=litellm_service,
        model_registry_service=_FakeModelRegistryService([_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
    )

    result = backend.rerank(
        query=RetrievalQuery(
            query_id="rq-rerank",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        candidates=CrossEncoderReranker.build_candidates(_retrieval_result()),
        top_n=2,
    )

    assert result.items[0].hit_id == "chunk-b"
    assert result.model_name == "rerank-v4.0"
    assert result.provider_id == "provider-rerank"
    assert litellm_service.calls
    assert litellm_service.calls[0]["documents"][1].startswith("Context:")


def test_cross_encoder_candidates_preserve_page_and_image_metadata():
    candidates = CrossEncoderReranker.build_candidates(_retrieval_result())

    assert candidates[0].page_ref is None
    assert candidates[0].image_caption is None
    enriched_hit = _retrieval_result().hits[1].model_copy(
        update={
            "metadata": {
                **_retrieval_result().hits[1].metadata,
                "page_ref": "VII (7)",
                "image_caption": "Moon gate diagram.",
            }
        }
    )
    candidates = CrossEncoderReranker.build_candidates(
        _retrieval_result().model_copy(
            update={"hits": [_retrieval_result().hits[0], enriched_hit]}
        )
    )

    assert candidates[1].page_ref == "VII (7)"
    assert candidates[1].image_caption == "Moon gate diagram."


def test_hosted_reranker_resolver_supports_explicit_model_and_provider():
    resolver = HostedRerankerResolver(
        model_registry_service=_FakeModelRegistryService([_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
        model_id="model-rerank",
        provider_id="provider-rerank",
    )

    target = resolver.resolve_target()

    assert target is not None
    assert target.model_id == "model-rerank"
    assert target.provider_id == "provider-rerank"


def test_hosted_reranker_resolver_uses_capability_probe_when_registry_caps_missing():
    resolver = HostedRerankerResolver(
        model_registry_service=_FakeModelRegistryService([_model_entry(capabilities=["text"])]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
        capability_probe=lambda provider_type, model_name: {
            "known": True,
            "mode": "rerank",
            "rerank": True,
        },
    )

    target = resolver.resolve_target()

    assert target is not None
    assert target.model_id == "model-rerank"


def test_hosted_reranker_resolver_does_not_guess_from_model_name_only():
    resolver = HostedRerankerResolver(
        model_registry_service=_FakeModelRegistryService([_model_entry(capabilities=["text"])]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
        capability_probe=lambda provider_type, model_name: {"known": False},
    )

    target = resolver.resolve_target()

    assert target is None


def test_hosted_reranker_resolver_rejects_provider_mismatch():
    resolver = HostedRerankerResolver(
        model_registry_service=_FakeModelRegistryService([_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
        model_id="model-rerank",
        provider_id="provider-other",
    )

    target = resolver.resolve_target()

    assert target is None


def test_hosted_reranker_resolver_accepts_openai_compatible_rerank_provider():
    resolver = HostedRerankerResolver(
        model_registry_service=_FakeModelRegistryService([_openai_rerank_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_openai_provider_entry()]),
        model_id="model-openai-rerank",
        provider_id="provider-openai-rerank",
    )

    target = resolver.resolve_target()

    assert target is not None
    assert target.model_id == "model-openai-rerank"
    assert target.provider_id == "provider-openai-rerank"


def test_local_cross_encoder_resolver_resolves_supported_local_model():
    resolver = LocalCrossEncoderResolver(
        model_registry_service=_FakeModelRegistryService([_local_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_local_provider_entry()]),
    )

    target = resolver.resolve_target()

    assert target is not None
    assert target.model_id == "model-local-rerank"
    assert target.provider_id == "provider-local-rerank"


def test_local_cross_encoder_resolver_requires_declared_rerank_capability():
    resolver = LocalCrossEncoderResolver(
        model_registry_service=_FakeModelRegistryService([_local_model_entry(capabilities=["text"])]),
        provider_registry_service=_FakeProviderRegistryService([_local_provider_entry()]),
    )

    target = resolver.resolve_target()

    assert target is None


@pytest.mark.asyncio
async def test_cross_encoder_reranker_uses_backend_scores_when_available():
    backend = HostedRerankerBackend(
        litellm_service=_FakeLiteLLMService(
            response={"results": [{"index": 1, "relevance_score": 0.93}, {"index": 0, "relevance_score": 0.35}]}
        ),
        model_registry_service=_FakeModelRegistryService([_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
    )
    reranker = CrossEncoderReranker(backend=backend)

    result = await reranker.rerank(
        query=RetrievalQuery(
            query_id="rq-rerank",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        result=_retrieval_result(),
    )

    assert result.hits[0].hit_id == "chunk-b"
    assert result.hits[0].score == 0.93
    assert result.trace is not None
    assert result.trace.reranker_name == "cross_encoder_hosted"
    assert result.trace.details["rerank"]["backend_name"] == "hosted"
    assert result.trace.details["rerank"]["model_id"] == "model-rerank"
    assert result.trace.details["rerank"]["provider_id"] == "provider-rerank"
    assert result.trace.details["rerank"]["resolution_source"] == "registry_capability"
    assert result.trace.details["rerank"]["used_backend_result"] is True


def test_local_cross_encoder_backend_uses_local_scorer_when_available():
    class _FakeLocalModel:
        def predict(self, pairs):
            assert pairs[0][1].startswith("Context:")
            return [0.35, 0.94]

    backend = LocalCrossEncoderBackend(
        model_registry_service=_FakeModelRegistryService([_local_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_local_provider_entry()]),
        cross_encoder_factory=lambda model_name: _FakeLocalModel(),
    )

    result = backend.rerank(
        query=RetrievalQuery(
            query_id="rq-local",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        candidates=CrossEncoderReranker.build_candidates(_retrieval_result()),
        top_n=2,
    )

    assert result.backend_name == "local_cross_encoder"
    assert result.items[0].hit_id == "chunk-b"
    assert result.model_name == "local-cross-encoder"


def test_local_cross_encoder_backend_accepts_array_like_scores():
    class _ArrayLikeScores:
        def __iter__(self):
            return iter([0.35, 0.94])

        def tolist(self):
            return [0.35, 0.94]

    class _FakeLocalModel:
        def predict(self, pairs):
            return _ArrayLikeScores()

    backend = LocalCrossEncoderBackend(
        model_registry_service=_FakeModelRegistryService([_local_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_local_provider_entry()]),
        cross_encoder_factory=lambda model_name: _FakeLocalModel(),
    )

    result = backend.rerank(
        query=RetrievalQuery(
            query_id="rq-local-array",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        candidates=CrossEncoderReranker.build_candidates(_retrieval_result()),
        top_n=2,
    )

    assert result.backend_name == "local_cross_encoder"
    assert result.items[0].hit_id == "chunk-b"
    assert result.warnings == []


@pytest.mark.asyncio
async def test_cross_encoder_reranker_uses_local_backend_when_hosted_unavailable():
    class _FakeLocalModel:
        def predict(self, pairs):
            return [0.22, 0.88]

    backend_chain = RerankerBackendChain(
        [
            HostedRerankerBackend(
                litellm_service=_FakeLiteLLMService(),
                model_registry_service=_FakeModelRegistryService([_non_rerank_model_entry()]),
                provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
            ),
            LocalCrossEncoderBackend(
                model_registry_service=_FakeModelRegistryService([_local_model_entry()]),
                provider_registry_service=_FakeProviderRegistryService([_local_provider_entry()]),
                cross_encoder_factory=lambda model_name: _FakeLocalModel(),
            ),
        ]
    )
    reranker = CrossEncoderReranker(backend=backend_chain)

    result = await reranker.rerank(
        query=RetrievalQuery(
            query_id="rq-rerank",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        result=_retrieval_result(),
    )

    assert result.hits[0].hit_id == "chunk-b"
    assert "rerank_backend_unavailable:no_supported_model" in result.warnings
    assert result.trace is not None
    assert result.trace.reranker_name == "cross_encoder_local_cross_encoder"
    assert result.trace.details["rerank"]["backend_name"] == "local_cross_encoder"
    assert result.trace.details["rerank"]["used_backend_result"] is True


@pytest.mark.asyncio
async def test_cross_encoder_reranker_degrades_to_metadata_when_backend_unavailable():
    backend = HostedRerankerBackend(
        litellm_service=_FakeLiteLLMService(),
        model_registry_service=_FakeModelRegistryService([_non_rerank_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
    )
    reranker = CrossEncoderReranker(backend=backend)

    result = await reranker.rerank(
        query=RetrievalQuery(
            query_id="rq-rerank",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        result=_retrieval_result(),
    )

    assert result.hits[0].hit_id == "chunk-b"
    assert "rerank_backend_unavailable:no_supported_model" in result.warnings
    assert result.trace is not None
    assert result.trace.reranker_name == "simple_metadata"
    assert result.trace.details["rerank"]["backend_name"] == "hosted"
    assert result.trace.details["rerank"]["used_backend_result"] is False


@pytest.mark.asyncio
async def test_cross_encoder_reranker_degrades_when_backend_result_is_incomplete():
    backend = HostedRerankerBackend(
        litellm_service=_FakeLiteLLMService(
            response={"results": [{"index": 1, "relevance_score": 0.93}]}
        ),
        model_registry_service=_FakeModelRegistryService([_model_entry()]),
        provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
    )
    reranker = CrossEncoderReranker(backend=backend)

    result = await reranker.rerank(
        query=RetrievalQuery(
            query_id="rq-rerank-incomplete",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        result=_retrieval_result(),
    )

    assert result.hits[0].hit_id == "chunk-b"
    assert result.trace is not None
    assert result.trace.reranker_name == "simple_metadata"
    assert "rerank_backend_incomplete:expected_2_got_1" in result.warnings
    assert result.trace.details["rerank"]["backend_name"] == "hosted"
    assert result.trace.details["rerank"]["returned_item_count"] == 1
    assert result.trace.details["rerank"]["used_backend_result"] is False


@pytest.mark.asyncio
async def test_backend_chain_skips_incomplete_hosted_result_and_uses_local_backend():
    class _FakeLocalModel:
        def predict(self, pairs):
            return [0.22, 0.88]

    backend_chain = RerankerBackendChain(
        [
            HostedRerankerBackend(
                litellm_service=_FakeLiteLLMService(
                    response={"results": [{"index": 1, "relevance_score": 0.91}]}
                ),
                model_registry_service=_FakeModelRegistryService([_model_entry()]),
                provider_registry_service=_FakeProviderRegistryService([_provider_entry()]),
            ),
            LocalCrossEncoderBackend(
                model_registry_service=_FakeModelRegistryService([_local_model_entry()]),
                provider_registry_service=_FakeProviderRegistryService([_local_provider_entry()]),
                cross_encoder_factory=lambda model_name: _FakeLocalModel(),
            ),
        ]
    )
    reranker = CrossEncoderReranker(backend=backend_chain)

    result = await reranker.rerank(
        query=RetrievalQuery(
            query_id="rq-rerank-chain",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        result=_retrieval_result(),
    )

    assert result.hits[0].hit_id == "chunk-b"
    assert "rerank_backend_incomplete:expected_2_got_1" in result.warnings
    assert result.trace is not None
    assert result.trace.reranker_name == "cross_encoder_local_cross_encoder"
    assert result.trace.details["rerank"]["backend_name"] == "local_cross_encoder"
    assert result.trace.details["rerank"]["used_backend_result"] is True


@pytest.mark.asyncio
async def test_llm_reranker_uses_gateway_order_when_available():
    gateway = _FakeStoryLlmGateway(
        response_text='{"ordered_hit_ids":["chunk-b","chunk-a"]}'
    )
    reranker = LLMReranker(
        model_id="model-rerank",
        provider_id="provider-rerank",
        gateway=gateway,
        model_registry_service=_FakeModelRegistryService([_model_entry(capabilities=["text"])]),
    )

    result = await reranker.rerank(
        query=RetrievalQuery(
            query_id="rq-llm-rerank",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        result=_retrieval_result(),
    )

    assert result.hits[0].hit_id == "chunk-b"
    assert result.trace is not None
    assert result.trace.reranker_name == "llm"
    assert result.trace.details["rerank"]["backend_name"] == "llm"
    assert result.trace.details["rerank"]["model_id"] == "model-rerank"
    assert result.trace.details["rerank"]["provider_id"] == "provider-rerank"
    assert result.trace.details["rerank"]["used_backend_result"] is True
    assert gateway.calls
    messages = gateway.calls[0]["messages"]
    assert isinstance(messages[0], ChatMessage)
    assert "ordered_hit_ids" in str(messages[0].content)


@pytest.mark.asyncio
async def test_llm_reranker_degrades_when_unconfigured():
    reranker = LLMReranker(
        gateway=_FakeStoryLlmGateway(),
        model_registry_service=_FakeModelRegistryService([_model_entry(capabilities=["text"])]),
    )

    result = await reranker.rerank(
        query=RetrievalQuery(
            query_id="rq-llm-unconfigured",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        result=_retrieval_result(),
    )

    assert result.hits[0].hit_id == "chunk-b"
    assert "llm_rerank_unconfigured:no_model_id" in result.warnings
    assert result.trace is not None
    assert result.trace.reranker_name == "simple_metadata"
    assert result.trace.details["rerank"]["backend_name"] == "llm"
    assert result.trace.details["rerank"]["used_backend_result"] is False


@pytest.mark.asyncio
async def test_llm_reranker_degrades_on_invalid_payload():
    reranker = LLMReranker(
        model_id="model-rerank",
        provider_id="provider-rerank",
        gateway=_FakeStoryLlmGateway(response_text="not json"),
        model_registry_service=_FakeModelRegistryService([_model_entry(capabilities=["text"])]),
    )

    result = await reranker.rerank(
        query=RetrievalQuery(
            query_id="rq-llm-invalid",
            query_kind="archival",
            story_id="story-rerank",
            domains=[Domain.WORLD_RULE],
            text_query="moon gate ritual",
            rerank=True,
        ),
        result=_retrieval_result(),
    )

    assert result.hits[0].hit_id == "chunk-b"
    assert "llm_rerank_failed:invalid_json" in result.warnings
    assert result.trace is not None
    assert result.trace.reranker_name == "simple_metadata"
    assert result.trace.details["rerank"]["backend_name"] == "llm"
    assert result.trace.details["rerank"]["used_backend_result"] is False
