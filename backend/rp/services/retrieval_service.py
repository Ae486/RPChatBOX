"""Top-level retrieval search service."""

from __future__ import annotations

from collections.abc import Sequence

from rp.models.memory_crud import RetrievalQuery, RetrievalSearchResult
from rp.retrieval.embedder import Embedder
from rp.retrieval.fusion_strategy import RrfFusionStrategy
from rp.retrieval.graph_expansion import (
    GraphExpansionRetriever,
    attach_skipped_graph_summary,
    graph_expansion_should_run,
    merge_graph_expansion_result,
)
from rp.retrieval.keyword_retriever import KeywordRetriever
from rp.retrieval.pipeline_slots import (
    FusionStrategy,
    QueryPreprocessor,
    ResultBuilder,
    Retriever,
    Reranker,
)
from rp.retrieval.pipeline_runner import retrieve_and_fuse
from rp.retrieval.query_preprocessor import DefaultQueryPreprocessor
from rp.retrieval.rag_context_builder import RagContextBuilder
from rp.retrieval.reranker_backends import (
    HostedRerankerBackend,
    LocalCrossEncoderBackend,
    RerankerBackendChain,
)
from rp.retrieval.result_builder import ChunkResultBuilder, DocumentResultBuilder
from rp.retrieval.reranker import CrossEncoderReranker
from rp.retrieval.semantic_retriever import SemanticRetriever
from services.langfuse_service import get_langfuse_service
from .retrieval_runtime_config_service import RetrievalRuntimeConfigService
from .retrieval_observability_service import RetrievalObservabilityService


class RetrievalService:
    """Provide chunk, document, and RAG retrieval views over the same store."""

    def __init__(
        self,
        session,
        *,
        embedder: Embedder | None = None,
        query_preprocessor: QueryPreprocessor | None = None,
        retrievers: Sequence[Retriever] | None = None,
        fusion_strategy: FusionStrategy | None = None,
        reranker: Reranker | None = None,
        chunk_result_builder: ResultBuilder | None = None,
        document_result_builder: ResultBuilder | None = None,
        rag_context_builder: RagContextBuilder | None = None,
        retrieval_runtime_config_service: RetrievalRuntimeConfigService | None = None,
        langfuse_service=None,
    ) -> None:
        self._session = session
        self._embedder = embedder
        self._query_preprocessor = query_preprocessor or DefaultQueryPreprocessor()
        self._retrievers = tuple(retrievers) if retrievers is not None else None
        self._fusion_strategy = fusion_strategy or RrfFusionStrategy()
        self._reranker = reranker
        self._chunk_result_builder = chunk_result_builder or ChunkResultBuilder()
        self._document_result_builder = (
            document_result_builder or DocumentResultBuilder()
        )
        self._rag_builder = rag_context_builder or RagContextBuilder()
        self._retrieval_runtime_config_service = (
            retrieval_runtime_config_service or RetrievalRuntimeConfigService(session)
        )
        self._langfuse = langfuse_service or get_langfuse_service()

    async def search_chunks(self, query: RetrievalQuery) -> RetrievalSearchResult:
        normalized_query = self._query_preprocessor.preprocess(query)
        with self._langfuse.start_as_current_observation(
            name="rp.retrieval.search_chunks",
            as_type="chain",
            input=self._build_observation_input(
                query=query, normalized_query=normalized_query
            ),
        ) as observation:
            try:
                result = await self._search_chunks_preprocessed(normalized_query)
            except Exception as exc:
                observation.update(
                    output=self._build_error_output(
                        query=normalized_query,
                        search_kind="chunks",
                        error=exc,
                    )
                )
                raise
            observation.update(
                output=self._build_result_output(
                    query=normalized_query,
                    result=result,
                    search_kind="chunks",
                )
            )
            return result

    async def search_documents(self, query: RetrievalQuery) -> RetrievalSearchResult:
        normalized_query = self._query_preprocessor.preprocess(query)
        with self._langfuse.start_as_current_observation(
            name="rp.retrieval.search_documents",
            as_type="chain",
            input=self._build_observation_input(
                query=query, normalized_query=normalized_query
            ),
        ) as observation:
            try:
                chunk_result = await self._search_chunks_preprocessed(normalized_query)
                result = self._document_result_builder.build(
                    query=normalized_query, result=chunk_result
                )
            except Exception as exc:
                observation.update(
                    output=self._build_error_output(
                        query=normalized_query,
                        search_kind="documents",
                        error=exc,
                    )
                )
                raise
            observation.update(
                output=self._build_result_output(
                    query=normalized_query,
                    result=result,
                    search_kind="documents",
                )
            )
            return result

    async def rag_context(self, query: RetrievalQuery) -> RetrievalSearchResult:
        normalized_query = self._query_preprocessor.preprocess(query)
        with self._langfuse.start_as_current_observation(
            name="rp.retrieval.rag_context",
            as_type="chain",
            input=self._build_observation_input(
                query=query, normalized_query=normalized_query
            ),
        ) as observation:
            try:
                chunk_result = await self._search_chunks_preprocessed(normalized_query)
                result = self._rag_builder.build(chunk_result)
            except Exception as exc:
                observation.update(
                    output=self._build_error_output(
                        query=normalized_query,
                        search_kind="rag",
                        error=exc,
                    )
                )
                raise
            observation.update(
                output=self._build_result_output(
                    query=normalized_query,
                    result=result,
                    search_kind="rag",
                )
            )
            return result

    async def _search_chunks_preprocessed(
        self, query: RetrievalQuery
    ) -> RetrievalSearchResult:
        retrievers, reranker = self._resolve_runtime_components(query)
        fused_result = await retrieve_and_fuse(
            query=query,
            retrievers=retrievers,
            fusion_strategy=self._fusion_strategy,
        )
        if graph_expansion_should_run(query):
            graph_result = await GraphExpansionRetriever(self._session).search(query)
            fused_result = merge_graph_expansion_result(
                query=query,
                result=fused_result,
                graph_result=graph_result,
            )
        else:
            fused_result = attach_skipped_graph_summary(
                query=query,
                result=fused_result,
            )
        reranked_result = await reranker.rerank(query=query, result=fused_result)
        return self._chunk_result_builder.build(query=query, result=reranked_result)

    def _resolve_runtime_components(
        self,
        query: RetrievalQuery,
    ) -> tuple[Sequence[Retriever], Reranker]:
        resolved_embedder = self._embedder or self._build_story_embedder(
            story_id=query.story_id
        )
        retrievers = self._retrievers or (
            KeywordRetriever(self._session),
            SemanticRetriever(self._session, embedder=resolved_embedder),
        )
        reranker = self._reranker or self._build_story_reranker(story_id=query.story_id)
        return retrievers, reranker

    def _build_story_embedder(self, *, story_id: str) -> Embedder:
        config = self._retrieval_runtime_config_service.resolve_story_config(
            story_id=story_id
        )
        return Embedder(
            model_id=config.embedding_model_id,
            provider_id=config.embedding_provider_id,
        )

    def _build_story_reranker(self, *, story_id: str) -> Reranker:
        config = self._retrieval_runtime_config_service.resolve_story_config(
            story_id=story_id
        )
        if not config.rerank_model_id and not config.rerank_provider_id:
            return CrossEncoderReranker()
        return CrossEncoderReranker(
            backend=RerankerBackendChain(
                [
                    HostedRerankerBackend(
                        model_id=config.rerank_model_id,
                        provider_id=config.rerank_provider_id,
                    ),
                    LocalCrossEncoderBackend(
                        model_id=config.rerank_model_id,
                        provider_id=config.rerank_provider_id,
                    ),
                ]
            )
        )

    @staticmethod
    def _build_observation_input(
        *,
        query: RetrievalQuery,
        normalized_query: RetrievalQuery,
    ) -> dict[str, object]:
        return {
            "query": query.model_dump(mode="json"),
            "normalized_query": normalized_query.model_dump(mode="json"),
        }

    def _build_result_output(
        self,
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
        search_kind: str,
    ) -> dict[str, object]:
        observability = RetrievalObservabilityService(self._session).build_view(
            query=query,
            result=result,
            include_story_snapshot=False,
            max_hits=3,
        )
        return {
            "status": "ok",
            "search_kind": search_kind,
            "observability": observability.model_dump(mode="json"),
        }

    @staticmethod
    def _build_error_output(
        *,
        query: RetrievalQuery,
        search_kind: str,
        error: Exception,
    ) -> dict[str, object]:
        return {
            "status": "error",
            "search_kind": search_kind,
            "query_id": query.query_id,
            "story_id": query.story_id,
            "query_kind": query.query_kind,
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        }
