# RP Authoritative Block Proposal Review Apply Visibility

## Scenario: Block-Scoped Proposal Detail and Manual Apply Continuation

### 1. Scope / Trigger

- Trigger: active-story memory Block routes already support proposal submit and list for authoritative Core State Blocks, but lack the next review/apply/visibility step.
- Applies to backend RP services and APIs that expose proposal detail and manual apply for `{session_id}/{block_id}/{proposal_id}`.
- This slice is a narrow continuation over the existing proposal/apply persistence. It does not create a new workflow, policy engine, or public `proposal.apply` tool family.
- Non-authoritative Block proposal detail/apply stays unsupported in this slice.

### 2. Signatures

Read-side detail shape:

```python
{
    "proposal_id": str,
    "status": str,
    "policy_decision": str | None,
    "domain": str,
    "domain_path": str | None,
    "operation_kinds": list[str],
    "created_at": datetime,
    "applied_at": datetime | None,
    "reason": str | None,
    "trace_id": str | None,
    "error_message": str | None,
    "operations": list[dict],
    "base_refs": list[dict],
    "apply_receipts": list[dict],
}
```

Services:

```python
class MemoryInspectionReadService:
    def get_proposal_for_authoritative_ref(
        self,
        *,
        story_id: str,
        target_ref: ObjectRef,
        proposal_id: str,
        session_id: str | None = None,
    ) -> dict | None: ...
```

```python
class StoryBlockMutationService:
    def apply_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        proposal_id: str,
    ) -> ProposalReceipt | None: ...
```

Controller:

```python
class StoryRuntimeController:
    def get_memory_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        proposal_id: str,
    ) -> dict | None: ...

    def apply_memory_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        proposal_id: str,
    ) -> dict | None: ...
```

APIs:

```http
GET  /api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/proposals/{proposal_id}
POST /api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/proposals/{proposal_id}/apply
```

Responses:

```python
{
    "session_id": str,
    "block_id": str,
    "proposal_id": str,
    "item": dict,
}
```

### 3. Contracts

- The Block-addressed detail/apply path must first resolve `{block_id}` through `RpBlockReadService.get_block(session_id=..., block_id=...)`.
- Unknown Block under an existing session reuses the existing `memory_block_not_found` behavior.
- Detail/apply lookup must remain exact-target and session-scoped:
  - same `story_id` as the resolved session
  - same `session_id` as the addressed story session
  - at least one operation targets the exact resolved authoritative Block identity
- Do not expose a proposal that exists for another session or another authoritative Block through this route.
- `MemoryInspectionReadService` must build the detail payload from the existing persisted records:
  - `ProposalRepository.get_proposal_record(...)`
  - `ProposalRepository.list_apply_receipts_for_proposal(...)`
  - the same authoritative target matching logic already used by block proposal list
- The detail payload must preserve canonical proposal visibility:
  - proposal status / policy decision / timestamps
  - canonical operation payloads and base refs
  - reason / trace id / error message
  - apply receipt summaries when the proposal has already been applied
- `StoryBlockMutationService.apply_block_proposal(...)` must reuse `ProposalApplyService.apply_proposal(...)`.
- Manual apply must not bypass the existing proposal/apply chain, and must not write directly to:
  - `StorySession.current_state_json`
  - Core State tables
  - projection mirrors
- Applying an already-applied proposal is idempotent in this slice. Replays may return the same proposal receipt/detail, and must not create extra apply receipts.
- After a successful apply, the updated proposal status and apply receipt must become visible from both:
  - `GET /memory/blocks/{block_id}/proposals`
  - `GET /memory/blocks/{block_id}/proposals/{proposal_id}`
- Do not replace `WritingPacketBuilder`.
- Do not move setup runtime-private cognition into durable story Memory OS.
- Do not rebuild Recall / Archival as Block storage.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Unknown `session_id` | Return HTTP 404 with `story_session_not_found` |
| Unknown `block_id` for an existing session | Return HTTP 404 with `memory_block_not_found` |
| Proposal does not belong to the addressed `{session_id}/{block_id}` authoritative target | Return HTTP 404 with `memory_block_proposal_not_found` |
| Resolved Block is non-authoritative (for example projection or runtime-workspace) and client tries to read detail/apply | Return HTTP 400 with `memory_block_mutation_unsupported` |
| Existing proposal apply fails in `ProposalApplyService` | Return HTTP 400 with a stable apply-failed error; do not remap to not-found |
| Valid authoritative detail read | Return HTTP 200 with the persisted detail payload and any existing apply receipts |
| Valid authoritative review-required proposal apply | Return HTTP 200 with the updated proposal detail, now visible as applied |

### 5. Good / Base / Bad Cases

- Good: GET a review-required `chapter.current` proposal through the exact authoritative Block route and inspect its canonical operations/base refs before approval.
- Good: POST apply on that same `{block_id}/{proposal_id}` reuses `ProposalApplyService`, transitions the proposal to `applied`, and exposes one apply receipt in the returned detail.
- Good: POST apply on an already-applied authoritative proposal returns the same applied detail without creating duplicate receipts.
- Base: the detail/apply route is only an addressed visibility/review surface over existing persisted proposal data.
- Bad: exposing a different Block's proposal detail because it shares the same domain.
- Bad: creating a new direct write path for manual apply instead of calling `ProposalApplyService.apply_proposal(...)`.
- Bad: inventing non-authoritative proposal detail/apply semantics in this slice.

### 6. Tests Required

- Successful authoritative Block proposal detail read:
  - returns HTTP 200 with canonical proposal payload, reason, trace fields, and empty/non-empty apply receipt list as appropriate
- Successful authoritative Block proposal apply:
  - returns HTTP 200 with applied detail
  - list route now shows `status == "applied"`
  - one apply receipt is visible in detail
- Exact-target/session isolation:
  - proposal from another Block or another session returns `memory_block_proposal_not_found`
- Unsupported mutation target:
  - projection/runtime-workspace Block detail is rejected with `memory_block_mutation_unsupported`
  - projection Block apply is rejected with `memory_block_mutation_unsupported`
- Not-found behavior:
  - missing session returns `story_session_not_found`
  - missing block returns `memory_block_not_found`
- Workflow preservation:
  - no direct state write path is introduced
  - apply continues to reuse the existing `ProposalApplyService` / repository persistence

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: trust proposal_id alone and apply it without checking the addressed block.
return proposal_apply_service.apply_proposal(proposal_id)
```

#### Correct

```python
# Correct: resolve the addressed Block, verify the proposal belongs to that
# exact authoritative target and session, then reuse the canonical apply path.
block = rp_block_read_service.get_block(session_id=session_id, block_id=block_id)
proposal = memory_inspection_read_service.get_proposal_for_authoritative_ref(
    story_id=session.story_id,
    session_id=session_id,
    target_ref=block_ref,
    proposal_id=proposal_id,
)
if proposal is None:
    raise MemoryBlockProposalNotFoundError(proposal_id)
receipt = proposal_apply_service.apply_proposal(proposal_id)
```
