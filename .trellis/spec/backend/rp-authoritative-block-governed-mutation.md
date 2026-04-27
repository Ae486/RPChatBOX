# RP Authoritative Block Governed Mutation

## Scenario: Block-Addressed Authoritative Mutation via Existing Proposal Workflow

### 1. Scope / Trigger

- Trigger: RP memory needs a write entry addressed by `{session_id}/{block_id}` for authoritative Core State Blocks.
- Applies to backend RP services and APIs that accept Block-addressed proposal submission.
- This slice is an adapter over the existing `ProposalSubmitInput` + `ProposalWorkflowService` path. It does not create a new mutation backend.
- Projection Block mutation stays unsupported in this slice.

### 2. Signatures

Request model:

```python
class MemoryBlockProposalSubmitRequest(BaseModel):
    operations: list[StatePatchOperation]
    base_refs: list[ObjectRef] = Field(default_factory=list)
    reason: str | None = None
    trace_id: str | None = None
```

Service:

```python
class StoryBlockMutationService:
    async def submit_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        payload: MemoryBlockProposalSubmitRequest,
    ) -> ProposalReceipt | None: ...
```

Controller:

```python
class StoryRuntimeController:
    async def submit_memory_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        payload: MemoryBlockProposalSubmitRequest,
    ) -> dict | None: ...
```

API:

```http
POST /api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/proposals
```

Response:

```python
{
    "session_id": str,
    "block_id": str,
    "item": ProposalReceipt,
}
```

### 3. Contracts

- The write path must first resolve `{block_id}` through `RpBlockReadService.get_block(session_id=..., block_id=...)`.
- Unknown Block under an existing session reuses the existing `memory_block_not_found` behavior.
- Only `Layer.CORE_STATE_AUTHORITATIVE` Blocks are writable in this slice.
- Projection Blocks must fail with a stable HTTP 400 error instead of inventing projection mutation semantics.
- Each submitted operation must target the exact resolved authoritative Block identity:
  - `object_id == block.label`
  - `layer == block.layer`
  - `domain == block.domain`
  - `domain_path == block.domain_path`
  - `scope == block.scope` after defaulting missing scope to `"story"`
- Validation happens at the Block-addressed entry point. Do not let mismatched operation refs flow into proposal persistence or apply.
- After validation, the adapter must normalize each operation target ref to the resolved authoritative Block ref before constructing the canonical `ProposalSubmitInput`. This is the only allowed mutation bridge in this slice.
- The canonical `ProposalSubmitInput` must be synthesized from:
  - `story_id`: resolved session `story_id`
  - `mode`: resolved session `mode`
  - `domain`: resolved Block `domain`
  - `domain_path`: resolved Block `domain_path`
  - `operations`: normalized operation list
  - `base_refs`, `reason`, `trace_id`: pass through from the request body
- Submission must go through the existing `ProposalWorkflowService.submit_and_route(...)`, carrying the resolved `session_id` and current `chapter_workspace_id` when available.
- The adapter must commit after success and after workflow exceptions so proposal status transitions match existing `ProposalService` semantics.
- GET `/memory/blocks/{block_id}/proposals` remains the read-side visibility surface. A successful POST in this slice must become visible there without adding new proposal storage/query code paths.
- Do not replace `WritingPacketBuilder`.
- Do not move setup runtime-private cognition into durable story Memory OS.
- Do not rebuild Recall / Archival as Block storage.
- Do not bypass proposal/apply with direct state writes.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Unknown `session_id` | Return HTTP 404 with `story_session_not_found` |
| Unknown `block_id` for an existing session | Return HTTP 404 with `memory_block_not_found` |
| Resolved Block is projection/non-authoritative | Return HTTP 400 with `memory_block_mutation_unsupported` |
| Any operation `target_ref` does not match the resolved authoritative Block identity | Return HTTP 400 with `memory_block_target_mismatch` |
| Canonical proposal validation fails after Block validation | Return HTTP 400 with a stable proposal-invalid error; do not remap to not-found |
| Valid authoritative submission routed to review | Return HTTP 200 with the created `ProposalReceipt` and persisted proposal record |
| Valid authoritative submission routed to apply | Return HTTP 200 with the resulting `ProposalReceipt`, still using the existing apply path |

### 5. Good / Base / Bad Cases

- Good: POST to an authoritative `chapter.current` Block with one `patch_fields` operation targeting the same `chapter.current` identity creates a proposal receipt through the existing workflow.
- Good: a client omits `scope` on the operation target ref, and the adapter still accepts it because the resolved authoritative Block scope defaults to `story`.
- Base: the route body reuses existing `StatePatchOperation` payloads; only the Block-addressed wrapper is new.
- Bad: accepting a `chapter.unrelated` target ref while the path resolves `chapter.current`.
- Bad: allowing a projection Block to mutate through the authoritative proposal/apply chain.
- Bad: writing directly to `StorySession.current_state_json`, Core State tables, or projection mirrors from the Block route.

### 6. Tests Required

- Successful authoritative Block POST:
  - returns HTTP 200 with `session_id`, `block_id`, and `ProposalReceipt`
  - persists a proposal visible from GET `/memory/blocks/{block_id}/proposals`
- Exact-target validation:
  - mismatched `target_ref.object_id` / `domain_path` / `domain` is rejected with `memory_block_target_mismatch`
- Unsupported mutation target:
  - projection Block POST is rejected with `memory_block_mutation_unsupported`
- Not-found behavior:
  - missing session returns `story_session_not_found`
  - missing block returns `memory_block_not_found`
- Workflow preservation:
  - no direct state write path is introduced
  - existing proposal/apply persistence is still the only mutation route

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: trust the body target_ref and write it directly.
input_model = ProposalSubmitInput(
    story_id=payload.story_id,
    mode=payload.mode,
    domain=payload.domain,
    domain_path=payload.domain_path,
    operations=payload.operations,
)
```

#### Correct

```python
# Correct: resolve the authoritative Block first, validate every operation
# against that exact identity, then normalize into the canonical workflow.
block = rp_block_read_service.get_block(session_id=session_id, block_id=block_id)
normalized_ops = [
    operation.model_copy(update={"target_ref": block_ref})
    for operation in payload.operations
]
input_model = ProposalSubmitInput(
    story_id=session.story_id,
    mode=session.mode,
    domain=block.domain,
    domain_path=block.domain_path,
    operations=normalized_ops,
    base_refs=payload.base_refs,
    reason=payload.reason,
    trace_id=payload.trace_id,
)
```
