# RP Runtime Workspace Turn Material Store

## Scenario: Typed current-turn material store before writer retrieval and workers depend on Runtime Workspace

### 1. Scope / Trigger

- Trigger: the memory contract registry and identity skeleton exist; the next story-runtime memory slice needs a shared typed shape for current-turn scratch, retrieval cards, usage records, rule cards, worker candidates, evidence bundles, packet refs, and trace material.
- Applies to backend RP Runtime Workspace contract work for:
  - material DTOs;
  - material lifecycle and visibility;
  - identity-scoped material lookup;
  - domain validation through the memory contract registry;
  - lightweight change-event emission for material creation / lifecycle updates;
  - focused model/service tests.
- This slice must not replace existing `StoryArtifact` / `StoryDiscussionEntry` Block views, add public memory tools, implement writer final-output gating, create durable DB tables, or promote Runtime Workspace material into Core State / Recall / Archival.

### 2. Signatures

Material kinds:

```text
writer_input_ref
writer_output_ref
retrieval_card
retrieval_expanded_chunk
retrieval_miss
retrieval_usage_record
rule_card
rule_state_card
review_overlay
worker_candidate
worker_evidence_bundle
post_write_trace
packet_ref
token_usage_metadata
```

Lifecycle states:

```text
active
used
unused
expanded
promoted
discarded
expired
invalidated
```

Runtime material envelope:

```python
class RuntimeWorkspaceMaterial(BaseModel):
    material_id: str
    material_kind: RuntimeWorkspaceMaterialKind
    identity: MemoryRuntimeIdentity
    domain: str
    domain_path: str | None
    source_refs: list[MemorySourceRef]
    short_id: str | None
    payload: dict[str, Any]
    lifecycle: RuntimeWorkspaceMaterialLifecycle
    visibility: str
    created_by: str
    expiration_ref: str | None
    materialization_ref: str | None
    metadata: dict[str, Any]
```

Service surface:

```python
class RuntimeWorkspaceMaterialService:
    def record_material(self, material: RuntimeWorkspaceMaterial) -> RuntimeWorkspaceMaterialReceipt: ...
    def get_material(self, *, identity: MemoryRuntimeIdentity, material_id: str) -> RuntimeWorkspaceMaterial | None: ...
    def require_material(self, *, identity: MemoryRuntimeIdentity, material_id: str) -> RuntimeWorkspaceMaterial: ...
    def list_materials(self, *, identity: MemoryRuntimeIdentity, material_kind: RuntimeWorkspaceMaterialKind | None = None, domain: str | None = None, lifecycle: RuntimeWorkspaceMaterialLifecycle | None = None) -> list[RuntimeWorkspaceMaterial]: ...
    def update_lifecycle(self, *, identity: MemoryRuntimeIdentity, material_id: str, lifecycle: RuntimeWorkspaceMaterialLifecycle, reason: str) -> RuntimeWorkspaceMaterialReceipt: ...
```

### 3. Contracts

#### Runtime Workspace ownership

- Runtime Workspace material is current-turn scratch, evidence, candidate, or trace material.
- It is not Core State truth.
- It is not Recall history.
- It is not Archival source material.
- It may later be promoted only through explicit governed paths such as proposal/apply, recall materialization, archival ingestion, or user review.
- Existing draft/discussion Block-compatible views remain read-only compatibility surfaces and are not replaced by this typed material service in this slice.

#### Identity contract

- Every material must carry `MemoryRuntimeIdentity`.
- The service must isolate reads and writes by full identity, not only `session_id`.
- A material recorded under one branch / turn / profile snapshot must not be returned for another identity.
- Missing or blank identity fields fail through `MemoryRuntimeIdentity` validation.

#### Domain and registry contract

- `domain` must resolve through `MemoryContractRegistryService`.
- Unknown domains fail closed with a stable service error.
- The service must not introduce a local domain allowlist.
- The service may accept future registry domains when a test-only registry is injected.

#### Short-id contract

- `short_id` is optional but, when provided, must be unique within one identity.
- The same `short_id` may exist under another full identity, including a different branch head, turn, or runtime profile snapshot.
- Short ids are writer-facing labels such as `R1`, `R2`, or `RULE1`; they are not durable truth ids.

#### Lifecycle contract

- Newly recorded material defaults to `active` unless explicitly supplied.
- Lifecycle updates return a lightweight `MemoryChangeEvent` that marks the material and any dirty targets.
- Lifecycle changes do not mutate Core State, Recall, or Archival.
- This slice does not enforce the future writer final-output usage gate; it only provides the typed material and lifecycle surface that the gate will consume.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Material has unknown domain | Reject with `runtime_workspace_domain_not_registered` |
| Material has blank `material_id`, `domain`, `created_by`, or `short_id` when provided | Pydantic validation fails |
| Same `short_id` recorded twice for one identity | Reject with `runtime_workspace_short_id_conflict` |
| Same `short_id` recorded for a different branch / turn / profile identity | Allowed |
| Material read with wrong branch / turn / profile identity | Returns `None` or raises not-found via `require_material` |
| Lifecycle update targets missing material | Reject with `runtime_workspace_material_not_found` |
| Lifecycle update succeeds | Returns updated material plus `MemoryChangeEvent` with full identity, layer `runtime_workspace`, material source ref, and visibility effect |
| Retrieval card is recorded | Stays Runtime Workspace material; no Core State / Recall / Archival mutation occurs |

### 5. Good / Base / Bad Cases

- Good: writer retrieval stores cards as `retrieval_card` materials with `short_id` values like `R1`, then records a later `retrieval_usage_record` material in the same identity.
- Good: a TRPG rule helper stores `rule_card` / `rule_state_card` material for the current turn without writing `Core State.authoritative_state`.
- Good: a worker candidate is represented as `worker_candidate` material until proposal/apply or review accepts it.
- Base: current draft artifacts and discussion entries still appear through existing Runtime Workspace Block views while the typed turn-material service exists beside them.
- Bad: treating retrieval cards as current truth because they are stored in Runtime Workspace.
- Bad: looking up material by `session_id` only and leaking a previous branch or turn into the active turn.
- Bad: adding a new public `memory.runtime_workspace.write` tool in this slice.

### 6. Tests Required

- Model tests cover all material kinds and lifecycle enum values.
- Service tests cover:
  - recording and listing materials by full identity;
  - full-identity isolation across branches / turns / profile snapshots;
  - domain registry validation and test-only registry extension;
  - short-id uniqueness within one identity and reuse across different branch / turn / profile identities;
  - lifecycle update receipts and emitted `MemoryChangeEvent`;
  - retrieval cards / worker candidates remaining Runtime Workspace material only.
- Focused lint/type checks must include the new models, service, and tests.

### 7. Wrong vs Correct

#### Wrong

```python
materials_by_session[session_id].append(raw_hit)
```

This stores raw hits by session only, so branch / turn / profile isolation and usage tracing cannot be enforced.

#### Correct

```python
service.record_material(
    RuntimeWorkspaceMaterial(
        identity=turn_identity,
        material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
        domain="knowledge_boundary",
        short_id="R1",
        payload=card_payload,
        created_by="writer.retrieval",
    )
)
```

The material is typed, identity-scoped, domain-validated, and still explicitly not story truth.

#### Wrong

```python
core_state["character_state_digest"].update(worker_candidate.payload)
```

This lets temporary worker material mutate truth without governance.

#### Correct

```python
candidate = service.record_material(worker_candidate_material)
```

The worker candidate remains Runtime Workspace material until a later governed proposal/apply or review path consumes it.

## Scenario: First-stage longform runtime acceptance proves the minimal runnable loop

### 1. Scope / Trigger

- Trigger: first-stage story runtime acceptance must prove an actual longform writing turn loop, not just isolated material DTO behavior.
- Applies when backend changes touch story graph runner finalize, writer packet/material persistence, draft artifact production, post-write settlement, rewrite/adoption continuation base, or rollback-visible read scope.
- This scenario must not expand into full branch UI, physical purge, branch merge, cross-branch Story Evolution, or full roleplay/TRPG runtime.

### 2. Signatures

The first-stage longform acceptance path must be able to observe these backend surfaces:

```text
StoryGraphRunner stream/non-stream turn execution
StoryTurnRecord.status / acceptance / settlement fields
RuntimeWorkspaceMaterial kinds:
  writer_input_ref
  packet_ref
  writer_output_ref
  token_usage_metadata
StoryArtifact kind:
  story_segment draft
Branch metadata:
  graph_checkpoint_binding
  graph_checkpoint_bindings_by_turn_id[turn_id]
Draft selection/adoption:
  selection receipt
  adoption receipt
  canonical_continuation_base
```

### 3. Contracts

#### Minimal runnable loop contract

- A first-stage longform writing turn is runnable only when the test can prove:
  - the user writing command/prompt reaches the writer packet;
  - the writer produces a `story_segment` draft artifact;
  - Runtime Workspace records `writer_input_ref`, `packet_ref`, `writer_output_ref`, and `token_usage_metadata` with useful payloads and source refs;
  - post-write/job settlement reaches `settled` or an explicitly allowed deferred/accepted state;
  - graph checkpoint binding is captured only as a technical anchor.
- Counting materials is insufficient. Tests must assert payload content, identity, source refs, lifecycle, and settlement state.

#### Continuation-base contract

- `selection` is reversible UI/runtime state and is not adoption.
- Only an `accept_and_continue` adoption receipt may create or update `canonical_continuation_base`.
- Unadopted rewrite/revision candidates must not become the next continuation base, even if they are selected or visible in the review surface.

#### Rollback acceptance contract

- Rollback acceptance must prove active branch truth, not only receipt shape:
  - `BranchHead.head_turn_id` and `last_settled_turn_id` return to the target turn;
  - later turns become `hidden_by_rollback`;
  - later Runtime Workspace materials become invalidated or hidden from active branch reads;
  - branch-visible chapter snapshots do not expose cutoff-after artifacts, discussion entries, or pending pointers.
- `graph_checkpoint_binding` is a one-time checkpoint/debug anchor. It never replaces application-layer settled/job-ledger/visibility checks.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Writer packet omits the user command/prompt | Acceptance test fails; minimal loop is not proven |
| `story_segment` draft is absent | Acceptance test fails |
| Runtime Workspace has material rows but missing payload/source refs | Acceptance test fails |
| Turn ends without settled or allowed deferred/accepted state | Acceptance test fails |
| A selected but unadopted candidate exists | It is not used as `canonical_continuation_base` |
| `accept_and_continue` adopts a candidate | Adopted draft becomes `canonical_continuation_base` |
| Rollback targets a turn with checkpoint binding | Receipt carries the target binding as technical metadata |
| Rollback targets a turn without binding | Rollback still succeeds through application visibility and records a stable missing reason |
| Later branch material appears in active branch snapshot after rollback | Acceptance test fails |

### 5. Good / Base / Bad Cases

- Good: a focused graph-runner test asserts writer input payload, packet payload, output payload, token usage payload, source refs, draft artifact kind, turn settlement, and checkpoint binding.
- Good: a draft-selection test asserts selection alone does not affect the continuation base, then `accept_and_continue` does.
- Good: a rollback test asserts both branch head state and active branch read snapshots after rollback.
- Base: post-write may be explicitly deferred when policy allows it, but the deferred state must be recorded and visible to the next-turn gate.
- Bad: declaring the first-stage runtime complete because a service inserted any `writer_output_ref`.
- Bad: treating a selected rewrite candidate as adopted continuation truth.
- Bad: using LangGraph replay/fork checkpoint state as proof that RP branch visibility is correct.

### 6. Tests Required

- Longform minimal loop test must assert:
  - writer command/prompt enters packet;
  - `story_segment` draft and pending pointer are produced when expected;
  - `writer_input_ref / packet_ref / writer_output_ref / token_usage_metadata` payloads and source refs are inspectable;
  - settlement/deferred state is explicit;
  - graph checkpoint binding exists for settled turns.
- Revision/adoption tests must assert:
  - selection can exist without adoption;
  - unadopted candidates are ignored by the next continuation base;
  - adopted candidates become the canonical continuation base.
- Branch/rollback regression tests must assert:
  - checkpoint binding is carried or missing reason is recorded;
  - repeated checkpoint capture is idempotent;
  - later turns/materials/read snapshots do not pollute the active branch after rollback.
- Focused lint/type checks must include graph runner, turn-domain, identity service, draft selection, and projection/graph-runner tests when those surfaces change.

### 7. Wrong vs Correct

#### Wrong

```python
materials = workspace.list_materials(identity=identity)
assert materials
```

This proves only that some Runtime Workspace rows exist. It does not prove that the user prompt reached the writer, that the draft is usable, or that the turn is safe for continuation.

#### Correct

```python
writer_input = workspace.require_material(identity=identity, material_id=turn.writer_input_ref)
packet = workspace.require_material(identity=identity, material_id=turn.packet_ref)
writer_output = workspace.require_material(identity=identity, material_id=turn.writer_output_ref)

assert "WRITE_NEXT_SEGMENT" in writer_input.payload["user_prompt"]
assert packet.payload["identity"]["turn_id"] == identity.turn_id
assert writer_output.payload["artifact_kind"] == "story_segment"
assert turn.status in {"settled", "post_write_deferred"}
```

The test proves the runnable loop contract: input, packet, output, material identity, and settlement all line up.

#### Wrong

```python
chapter.pending_segment_artifact_id = selected_candidate_id
```

This promotes selection state into continuation truth without adoption.

#### Correct

```python
selection = selection_service.select_candidate(candidate_id)
assert selection.adoption_receipt_id is None

adoption = selection_service.accept_and_continue(selected_candidate_id=candidate_id)
assert adoption.canonical_continuation_base == candidate_id
```

Selection stays reversible; only explicit adoption updates the continuation base.
