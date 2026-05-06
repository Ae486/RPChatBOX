# RP Retrieval Card Usage And Promotion Boot Contract

## Scenario: bounded writer retrieval becomes traceable Runtime Workspace material before post-write maintenance depends on evidence-backed source refs

### 1. Scope / Trigger

- Trigger: branch-aware identity, persistent Runtime Workspace, persistent event records, and read-manifest boundaries are now strong enough that retrieval can stop being a pure query side effect. Boot-bar runtime needs a minimum closed loop from search -> card -> optional expansion -> usage -> post-write source refs.
- Applies to backend RP retrieval/runtime contract work for:
  - Runtime Workspace retrieval cards;
  - expansion of already-returned cards/chunks;
  - retrieval miss recording;
  - writer usage record material;
  - post-write promotion source-ref contract;
  - focused boot-bar traceability tests.
- This slice must not:
  - allow retrieval hits to mutate Core truth directly;
  - replace `RetrievalBroker`;
  - inject raw retrieval dumps as the long-term packet contract;
  - add a new public retrieval tool family;
  - implement full worker-side retrieval automation.

### 2. Surfaces

Internal retrieval card loop surface:

```python
class RuntimeRetrievalCardService:
    async def search_to_cards(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        query: RetrievalQuery,
        actor: str,
    ) -> list[RuntimeWorkspaceMaterial]: ...
    async def expand_cards(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        card_material_ids: list[str],
        actor: str,
    ) -> list[RuntimeWorkspaceMaterial]: ...
    def record_writer_usage(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        used_card_ids: list[str],
        used_expanded_chunk_ids: list[str],
        missed_query_ids: list[str] | None = None,
        actor: str,
    ) -> RuntimeWorkspaceMaterial: ...
```

Minimum material kinds used:

```text
retrieval_card
retrieval_expanded_chunk
retrieval_miss
retrieval_usage_record
```

Post-write promotion source-ref contract:

```python
class WorkerSourceRefBundle(BaseModel):
    retrieval_card_material_ids: list[str]
    retrieval_expanded_chunk_material_ids: list[str]
    retrieval_usage_material_ids: list[str]
```

### 3. Contracts

#### Retrieval boundary contract

- `RetrievalBroker` remains the retrieval read boundary.
- Writer/runtime retrieval must not invent a second retrieval engine.
- Search results used by runtime must be materialized into Runtime Workspace cards before they can influence packet-visible retrieval context or post-write maintenance.

#### Card contract

- A retrieval hit entering runtime becomes a `retrieval_card` Runtime Workspace material with:
  - stable `short_id` within the active identity;
  - source refs/provenance refs;
  - summary/excerpt payload fit for packet-visible retrieval context;
  - no promotion into Core truth by that act alone.

#### Expansion contract

- Expansion can only target already-returned cards or chunks under the same identity.
- Expansion result becomes `retrieval_expanded_chunk` material.
- Expansion does not bypass the Runtime Workspace trace path.

#### Usage contract

- Writer usage must be recorded explicitly as `retrieval_usage_record`.
- Usage references exact card/chunk material ids, not inferred prose matching.
- Missed searches should be recorded as `retrieval_miss` material when the boot runtime path wants to preserve failed information-seeking traces.

#### Promotion contract

- Post-write maintenance may consume used retrieval refs as source refs when creating:
  - proposal candidates
  - projection refresh requests
  - Recall candidates
  - Archival evolution actions
- Retrieval hits/cards/usages do not directly become `Core State.authoritative_state`.
- Governed promotion remains proposal/apply or the appropriate maintenance/ingestion path.

#### Packet contract

- Packet-visible retrieval context should come from Runtime Workspace card summaries and selected expansions only.
- Raw retrieval dump injection is not the long-term writer contract.
- Read-manifest and packet contracts remain the deterministic envelope around selected retrieval cards/usages.

#### Boot minimum contract

- Boot-bar minimum closed loop is:
  - search result -> `retrieval_card`
  - optional expansion -> `retrieval_expanded_chunk`
  - explicit usage -> `retrieval_usage_record`
  - post-write source refs can point back to those materials
- Richer ranking UX, card expiration heuristics, and broad worker-side retrieval automation can follow later.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Recall/Archival search runs during a runtime turn | Queryable `retrieval_card` materials are persisted under the active identity |
| Writer asks to expand a card | `retrieval_expanded_chunk` material is created for that same identity |
| Writer uses cards/chunks | `retrieval_usage_record` is persisted with exact referenced ids |
| Search misses | Optional `retrieval_miss` material can be persisted |
| Post-write proposal is based on retrieval evidence | Source refs include Runtime Workspace retrieval card/chunk/usage material refs |
| Retrieval card exists but is unused | It can later expire/remain unused without becoming truth |
| Retrieval card enters packet | It remains Runtime Workspace material, not Core truth |

### 5. Good / Base / Bad Cases

- Good: a Recall search creates `R1`/`R2` cards, writer expands `R2`, then usage records exactly `R2` and the expanded chunk id.
- Good: a later proposal candidate can cite the usage/card refs that justified the change.
- Base: boot runtime only needs a bounded loop; it does not need full autonomous retrieval planning for every worker yet.
- Bad: letting a retrieval hit skip Runtime Workspace and write a Core fact directly.
- Bad: deriving usage only by NLP over final prose.
- Bad: passing raw retrieval dumps through the packet with no card ids or provenance mapping.

### 6. Tests Required

- Integration tests cover:
  - search -> card materialization;
  - card expansion -> expanded chunk materialization;
  - explicit usage record creation;
  - post-write source refs including retrieval material ids.
- Contract tests cover:
  - card short ids stay identity-scoped;
  - unused cards do not become truth;
  - retrieval hits cannot directly mutate Core truth through this path.
- Focused lint/type checks must include the retrieval loop contract and tests.

### 7. Wrong vs Correct

#### Wrong

```python
result = await retrieval_broker.search_recall(input_model)
packet.context_sections.append({"label": "retrieval_raw", "items": [hit.excerpt_text for hit in result.hits]})
```

This bypasses Runtime Workspace card traceability and gives no stable usage/promotion chain.

#### Correct

```python
cards = await runtime_retrieval_card_service.search_to_cards(
    identity=identity,
    query=query,
    actor="writer.retrieval",
)
```

The retrieval result first becomes identity-scoped Runtime Workspace card material, and later packet/usage/promotion steps can reference those stable ids.
