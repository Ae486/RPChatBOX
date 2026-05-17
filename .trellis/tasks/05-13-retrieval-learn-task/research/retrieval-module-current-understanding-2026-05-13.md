# Retrieval 模块当前理解

日期：2026-05-13
任务：`.trellis/tasks/05-13-retrieval-learn-task`
范围：只读了解当前 retrieval 模块，不实施代码改动。

## 结论

当前 retrieval 不是空壳，也不只是早期通用 RAG。当前代码已经形成了较完整的检索主链：

`MemoryOsService / tool surface -> RetrievalBroker -> RetrievalService -> QueryPreprocessor -> keyword + semantic retrievers -> RRF fusion -> optional graph expansion -> optional rerank -> result/rag/context/observability`

旧 cooperation 文档里列出的部分 gap 已经在当前 checkout 中被推进：broker rerank 策略、narrative/archival filters、deterministic narrative scoring、RAG context budget trace、runtime branch visibility、graph expansion、writer-side bounded retrieval loop 都已有实现与测试锚点。

## 模块分层

### 1. 公共入口层

- `backend/rp/services/memory_os_service.py`
  - 很薄的 facade，直接把 `get_state/get_summary/search_recall/search_archival/list_versions/read_provenance` 转给 `RetrievalBroker`。
- `backend/rp/services/retrieval_broker.py`
  - memory search 的统一入口。
  - 负责把 `MemorySearchRecallInput` / `MemorySearchArchivalInput` 转成 `RetrievalQuery`。
  - 同时承接 core state / projection / provenance 等读面，因此名字是 retrieval broker，但职责覆盖 Memory OS read broker。
  - 当前已支持 search policy 影响 rerank：
    - `search_policy.rerank="on"` 强制启用；
    - `"off"` 强制关闭；
    - `"auto"` 由 runtime config、snapshot-pinned runtime policy 或 profile default 决定；
    - `longform/roleplay/trpg` profile 可触发默认 rerank。
  - runtime identity 存在时，会移除 caller 传入的 branch override filter，并以 runtime identity / read manifest 做 authoritative branch visibility filtering。

### 2. 查询与 pipeline 层

- `backend/rp/models/memory_crud.py`
  - 定义 `RetrievalQuery`、`RetrievalHit`、`RetrievalTrace`、`RetrievalSearchResult`。
- `backend/rp/services/retrieval_service.py`
  - 顶层 search service。
  - 支持 `search_chunks`、`search_documents`、`rag_context`。
  - 默认组件：
    - `DefaultQueryPreprocessor`
    - `KeywordRetriever`
    - `SemanticRetriever`
    - `RrfFusionStrategy`
    - `CrossEncoderReranker`
    - `ChunkResultBuilder` / `DocumentResultBuilder`
    - `RagContextBuilder`
  - graph expansion 在 chunk search 的 fusion 之后、rerank 之前接入。

### 3. Retrieval core 组件层

- `backend/rp/retrieval/query_preprocessor.py`
  - 规范化 filter list、search policy、intent、boolean flags、domain path prefix、top_k。
  - 当前支持的关键 filter 包括：
    - Recall：`materialization_kinds`、`source_families`、`chapter_indices`、`scene_refs`、`character_refs`、`pov_character_refs`、`foreshadow_refs`、`foreshadow_statuses`、`branch_ids`、`canon_statuses`
    - Archival：`source_types`、`source_families`、`source_origins`、`workspace_ids`、`commit_ids`
    - common：`knowledge_collections`、`mapped_targets`、`domain_path_prefix`
- `backend/rp/retrieval/search_utils.py`
  - 统一 row-level filter 语义。
  - Recall/Archival 都是 chunk metadata 优先，asset metadata/column fallback。
  - 多个 filter key 是 AND，同一个 key 多值是 OR。
- `backend/rp/retrieval/keyword_retriever.py`
  - PostgreSQL FTS 优先，Python scoring fallback。
- `backend/rp/retrieval/semantic_retriever.py`
  - pgvector 优先，Python cosine fallback。
- `backend/rp/retrieval/fusion_strategy.py`
  - RRF 融合 keyword/semantic 路径。
- `backend/rp/retrieval/reranker.py`
  - 有 `NoOpReranker`、`SimpleMetadataReranker`、`CrossEncoderReranker`、`LLMReranker`。
  - `SimpleMetadataReranker` 已经不是纯 title/tag boost，它会处理 scene、character、POV、foreshadow、chapter distance、canon、branch 等 narrative scoring，并把规则写进 trace。
  - `CrossEncoderReranker` 有 hosted/local backend chain，失败时 fallback 到 deterministic metadata rerank 并保留 warning/trace。
- `backend/rp/retrieval/rag_context_builder.py`
  - 负责把 hits 压成 RAG/context 视图。
  - 当前支持 `search_policy.context_budget.max_tokens`、`per_source_family`、`per_domain`，并在 trace 中记录 selected/excluded。

### 4. 存储与入库层

- `backend/models/rp_retrieval_store.py`
  - 主要表：
    - `rp_knowledge_collections`
    - `rp_source_assets`
    - `rp_parsed_documents`
    - `rp_knowledge_chunks`
    - `rp_embedding_records`
    - `rp_index_jobs`
    - graph projection 相关 nodes/edges/evidence/jobs
  - 对 PostgreSQL 支持 pgvector、FTS、HNSW index；非 PG 使用 JSON/fallback。
- `backend/rp/services/retrieval_ingestion_service.py`
  - 入库链：`parse -> chunk -> embed -> index`。
  - 支持 ingest、reindex、retry failed job、backfill stub embeddings。
  - chunk 会挂 asset/index_job/commit provenance refs。
- `backend/rp/services/minimal_retrieval_ingestion_service.py`
  - setup accept commit 后的 facade。
  - 把 foundation entry / blueprint / imported asset 转成 archival seed sections。
  - retrieval ingestion 完成后队列化 graph extraction；graph queue 失败不回滚 setup commit ingestion。
- recall ingestion service family
  - `recall_summary_ingestion_service.py`
  - `recall_scene_transcript_ingestion_service.py`
  - `recall_continuity_note_ingestion_service.py`
  - `recall_character_long_history_ingestion_service.py`
  - `recall_detail_ingestion_service.py`
  - `recall_retired_foreshadow_ingestion_service.py`
  - 这些服务负责把 runtime/story materialization 写成 Recall 可检索材料。

### 5. Graph expansion

- `backend/rp/retrieval/graph_expansion.py`
  - 不是 public graph search tool。
  - 仅当 `query_kind == "archival"` 且 `filters.intent == "relation_lookup"` 时参与。
  - 从 graph nodes/edges/evidence 找 evidence chunk，作为 supplemental hits 合并回普通 retrieval result。
  - graph unavailable 时降级为 warning summary，不应打断检索主链。
- `backend/rp/services/memory_graph_projection_service.py`
  - 负责 graph projection job queue / rebuild / retry。
- `backend/rp/services/memory_graph_extraction_service.py`
  - 执行异步 graph extraction job。

### 6. Runtime / writer 使用层

- `backend/rp/services/runtime_retrieval_card_service.py`
  - 将 search result materialize 成 Runtime Workspace material：
    - retrieval card
    - expanded chunk
    - retrieval miss
    - retrieval usage record
  - writer 可见的是 card/expanded short id，不直接拿 raw retrieval hits。
- `backend/rp/services/writing_worker_retrieval_loop_service.py`
  - writer-side bounded tool loop。
  - 暴露给 writer 的工具只有：
    - `retrieval.search`
    - `retrieval.expand`
    - `retrieval.usage`
  - search 支持 recall/archival；expand 只能扩已有 card；usage 记录用过/没用/缺口。
  - final output 前如果发生过 retrieval generation，必须先提交 usage，否则 fail closed。
- `backend/rp/services/writing_worker_execution_service.py`
  - 默认 raw one-shot；只有 packet metadata `writer_retrieval_allowed=True` 且模型支持 tools 且注入了 `RuntimeRetrievalCardService` 时才走 bounded retrieval loop。
  - 默认最多 2 次 retrieval attempt，配置上限 clamp 到 3。

## 当前能力状态

| 能力 | 当前状态 |
|---|---|
| DB-backed retrieval store | 已有 |
| Keyword / FTS | 已有，含 fallback |
| Semantic / pgvector | 已有，含 fallback |
| Hybrid fusion | 已有 |
| Runtime-configured embedding/rerank | 已有 |
| Broker search policy rerank | 已有 |
| Recall source-family filters | 已有 |
| Narrative Recall filters | 已有 |
| Archival source filters | 已有 |
| Deterministic narrative scoring trace | 已有 |
| RAG context budget trace | 已有 |
| Runtime branch visibility filtering | 已有 |
| Graph expansion | 已有，内部 additive |
| Writer bounded retrieval loop | 已有，显式 opt-in |
| Usage recording / fail-closed guard | 已有 |
| Retrieval eval cases | 已有 ingestion/search/maintenance/policy cases |

## 仍需重点关注的问题

1. `RetrievalBroker` 现在职责很重，既是 memory read broker，又是 retrieval policy resolver，又做 branch visibility filtering。后续如果继续扩，容易变成多职责瓶颈。
2. narrative-aware 能力依赖上游 metadata。retrieval 不会也不应从文本中发明 `scene_ref/character_refs/branch_id/canon_status`；如果上游 materialization 不稳定，检索策略会表现不稳定。
3. graph expansion 当前是 text-first / relation_lookup 内部补充路径，不是完整图检索产品面。不要把它误判成已经具备完整 graph RAG。
4. writer retrieval loop 只有显式 opt-in，普通 story segment 仍应走 raw streaming。这是重要边界，不能把所有 writer 调用都默认 buffer。
5. context budget 目前在 `RagContextBuilder` 层，runtime/specialist 是否都稳定消费该 composed context，需要按具体调用链继续核实。

## 推荐后续阅读顺序

1. `backend/rp/services/retrieval_broker.py`
2. `backend/rp/services/retrieval_service.py`
3. `backend/rp/retrieval/query_preprocessor.py`
4. `backend/rp/retrieval/search_utils.py`
5. `backend/rp/retrieval/reranker.py`
6. `backend/rp/retrieval/rag_context_builder.py`
7. `backend/rp/retrieval/graph_expansion.py`
8. `backend/rp/services/retrieval_ingestion_service.py`
9. `backend/rp/services/minimal_retrieval_ingestion_service.py`
10. `backend/rp/services/runtime_retrieval_card_service.py`
11. `backend/rp/services/writing_worker_retrieval_loop_service.py`
12. `backend/rp/tests/test_retrieval_broker.py`
13. `backend/rp/tests/test_retrieval_service.py`
14. `backend/rp/tests/test_runtime_retrieval_card_service.py`
15. `backend/rp/tests/test_writing_worker_retrieval_loop_service.py`

## 当前任务下一步建议

如果后续要继续从 learn 进入实施，应先选一个窄 slice：

1. 检查 specialist/runtime 是否稳定消费 `rag_context` 的 composed context，而不是 raw hits。
2. 审查 `RetrievalBroker` 的职责边界，决定是否需要抽出 policy resolver / branch visibility filter service。
3. 对 eval cases 和 pytest 覆盖做一次矩阵核对，确认 specs 中每条 contract 都有现行测试。
