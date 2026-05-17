# Retrieval Runtime Tool Contract Development Spec

Date: 2026-05-17

## 1. Scope / Trigger

The retrieval quality tuning work has reached a usable baseline for structured
worldbook/setup retrieval. The next slice moves from retrieval algorithm quality
to the runtime tool contract used by writer, worker, and orchestrator.

This development spec implements the target LLM-facing retrieval contract
recorded in:

- `.trellis/spec/backend/rp-narrative-retrieval-policy-contract.md`
- `.trellis/tasks/05-13-retrieval-learn-task/artifacts/retrieval-runtime-tool-contract-notes-2026-05-17.md`

Out of scope:

- SetupAgent tools. `setup.memory.search` and `setup.memory.read_refs` stay
  independent.
- Production retrieval weight tuning against one benchmark dataset.
- Complex recall-vs-archival semantic deduplication.
- Letting the LLM choose recall/archival source, K values, route weights,
  filters, or rerank settings.

## 2. Implementation Goals

Primary goal:

- Replace writer-facing card/search_kind semantics with a standard RAG-style
  `retrieval.search` contract that returns clean Top-K `results`.

The LLM should provide only query expression:

```json
{
  "query": "林鸢和夜紫林的关系怎么样",
  "mode": "entity_relation",
  "lexical_anchors": ["林鸢", "夜紫林"],
  "semantic_predicates": ["关系"]
}
```
The LLM should receive only useful reading material:

```json
{
  "query": "林鸢和夜紫林的关系怎么样",
  "results": [
    {
      "result_id": "R1",
      "title": "林鸢 - 人际关系",
      "summary": "stored setup/archival summary if available",
      "excerpt": null,
      "text": "matched evidence text",
      "section": "人际关系"
    }
  ],
  "warnings": []
}
```
## 3. Likely Files

Contracts:

- `backend/rp/models/retrieval_runtime_contracts.py`

New or changed services:

- `backend/rp/services/runtime_retrieval_search_service.py`
- `backend/rp/services/writing_worker_retrieval_loop_service.py`

Possible helper modules if the service starts growing:

- `backend/rp/services/runtime_retrieval_source_policy_service.py`
- `backend/rp/services/runtime_retrieval_result_serializer.py`

Tests:

- `backend/rp/tests/test_writing_worker_retrieval_loop_service.py`
- `backend/rp/tests/test_runtime_retrieval_card_service.py` if existing runtime
  workspace material behavior is preserved or adapted
- New focused test file if cleaner:
  `backend/rp/tests/test_runtime_retrieval_search_service.py`

Do not place all logic into `writing_worker_retrieval_loop_service.py`. That file
should remain an orchestration/LLM loop adapter, not the owner of source routing,
result serialization, validation, and retrieval merging.

## 4. Contracts

### 4.1 Input DTO

Add or adapt:

```python
RuntimeRetrievalSearchInput
```

Fields:

- `query: str`
- `mode: Literal["entity", "entity_relation", "semantic", "mixed", "vague"] | None`
- `lexical_anchors: list[str]`
- `semantic_predicates: list[str]`

Validation:

- `query` must be non-blank.
- list fields trim and dedupe non-blank strings.
- unknown fields are forbidden.
- `search_kind`, `top_k`, `filters`, `rerank_top_n`, and route weights must be
  rejected at the LLM-facing schema.

### 4.2 Output DTO

Add:

```python
RuntimeRetrievalSearchResult
RuntimeRetrievalResultItem
```

Required output behavior:

- response root includes `query`, `results`, and `warnings`;
- result item includes only LLM-useful fields;
- `result_id` is a short stable reference within this tool response, such as
  `R1`, `R2`;
- `summary` is returned only if a stored setup/archival summary exists;
- fallback preview must be named `excerpt`, not `summary`;
- `text` contains bounded matched evidence text;
- `section` is a human-readable section label when known.

Forbidden in normal LLM-facing output:

- raw score/rank;
- hit/chunk/asset/collection ids;
- raw metadata/provenance;
- source routing such as `search_kind`;
- raw retrieval trace.

Backend trace and runtime workspace material may still keep those fields for
debugging/eval.

## 5. Source Policy

`retrieval.search` no longer accepts `search_kind`.

For writer main path:

- backend may search both recall and archival/setup/worldbook material;
- backend returns one unified Top-K `results` list;
- the LLM does not see source routing.

First implementation can use a simple backend-owned merge policy:

- call `RetrievalBroker.search_recall(...)` with `scope="story"`;
- call `RetrievalBroker.search_archival(...)`;
- merge the two ranked lists with stable rank fusion or another deterministic
  source merge;
- return the configured final Top-K.

Do not add complex cross-source semantic deduplication in this slice. Recall and
archival are considered complementary:

- recall: landed prose, story progress, outlines, runtime summaries;
- archival: setup/worldbook facts, character foundations, world rules.

Only keep deduplication already guaranteed by existing retrieval behavior or
exact same-hit/same-chunk identity if such information is naturally available
inside the backend.

## 6. Summary And Text Semantics

`summary` is not generated by retrieval. It comes from stored setup/archival
material.

Implementation must not call an LLM or summarizer to create query-time summaries.

Recommended extraction order:

1. read stored summary-like field from hit metadata or structured material if
   available;
2. otherwise omit `summary`;
3. provide bounded preview as `excerpt` when useful;
4. provide matched body/section evidence as `text`.

If current ingestion does not consistently store summary on hits, the first
implementation should keep `summary=None` and use `excerpt`/`text` honestly.

## 7. Engineering Constraints

- Keep contracts typed with Pydantic models. Avoid untyped dict contracts across
  service boundaries.
- Keep the writer loop thin. Put source policy and serialization in separate
  services/helpers.
- Keep retrieval ranking backend-owned. Do not introduce LLM rerank or model-side
  candidate selection.
- Preserve existing retrieval internals: keyword, semantic, RRF, rerank,
  Langfuse, trace, and retrieval broker compatibility.
- Do not remove legacy `memory.search_recall` / `memory.search_archival`; treat
  them as lower-level compatibility surfaces.
- Do not make the new tool depend on SetupAgent internals.
- Do not introduce a broad new dependency.
- Do not tune production logic specifically to the Gensokyo/MyGO/Harry Potter
  test sets.
- Keep tests focused on contract behavior and source-policy ownership.

## 8. Suggested Implementation Steps

1. Add DTOs to `retrieval_runtime_contracts.py`.
2. Add `RuntimeRetrievalSearchService`:
   - validates normalized input;
   - resolves writer source policy;
   - calls recall and archival broker paths;
   - merges ranked hits deterministically;
   - serializes clean `results`.
3. Adapt `WritingWorkerRetrievalLoopService`:
   - update `retrieval.search` tool schema;
   - remove `search_kind` from LLM-facing schema;
   - return `results`, not `cards`;
   - keep `retrieval.usage` only if required by existing guard behavior, but do
     not force complex LLM bookkeeping beyond current safeguards.
4. Preserve or adapt runtime workspace material only as backend trace/audit
   storage. Do not expose card terminology in the search response.
5. Add tests.
6. Run focused backend tests and `py_compile`.

## 9. Test Plan

Focused tests:

```powershell
cd backend
python -m pytest rp\tests\test_writing_worker_retrieval_loop_service.py -q
python -m pytest rp\tests\test_runtime_retrieval_search_service.py -q
```

If no new test file is created, replace the second command with the exact focused
tests added to existing files.

Contract checks:

```powershell
python -m py_compile rp\models\retrieval_runtime_contracts.py rp\services\writing_worker_retrieval_loop_service.py
```

If new services are added, include them in `py_compile`.

Diff check:

```powershell
git diff --check -- backend\rp\models\retrieval_runtime_contracts.py backend\rp\services\writing_worker_retrieval_loop_service.py backend\rp\tests
```

Expected assertions:

- `retrieval.search` accepts `query`, `mode`, `lexical_anchors`, and
  `semantic_predicates`.
- `retrieval.search` rejects `search_kind`, `top_k`, filters, and route weights.
- writer search works without the LLM selecting recall/archival.
- output uses `results`, not `cards`.
- output excludes raw ids, scores, metadata, provenance, source routing, and raw
  trace.
- fallback preview is `excerpt`, not fake `summary`.
- when no stored summary exists, response does not fabricate one.
- backend can preserve trace/audit material separately from the LLM-facing
  payload.

## 10. Wrong vs Correct

Wrong LLM-facing input:

```json
{
  "query": "林鸢和夜紫林的关系怎么样",
  "search_kind": "archival",
  "top_k": 20,
  "filters": {"source_families": ["foundation_entry"]},
  "rerank_top_n": 10
}
```

Correct LLM-facing input:

```json
{
  "query": "林鸢和夜紫林的关系怎么样",
  "mode": "entity_relation",
  "lexical_anchors": ["林鸢", "夜紫林"],
  "semantic_predicates": ["关系"]
}
```

Wrong LLM-facing output:

```json
{
  "cards": [
    {
      "short_id": "R1",
      "score": 0.82,
      "chunk_id": "chunk-123",
      "metadata": {"source_family": "archival"},
      "search_kind": "archival"
    }
  ]
}
```

Correct LLM-facing output:

```json
{
  "query": "林鸢和夜紫林的关系怎么样",
  "results": [
    {
      "result_id": "R1",
      "title": "林鸢 - 人际关系",
      "summary": null,
      "excerpt": "已有片段预览",
      "text": "召回命中的有效正文或 section 内容",
      "section": "人际关系"
    }
  ],
  "warnings": []
}
```
