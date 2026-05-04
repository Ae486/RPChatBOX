# RP Core State Base Revision Conflict Enforcement

## Scenario: Fail-closed authoritative apply when a proposal's base revision is stale

### 1. Scope / Trigger

- Trigger: proposal/apply already persists canonical proposal records and apply receipts, but the apply path does not yet reject stale base revisions. User edits and worker candidates need a hard fail-closed guard before later conflict-handling slices can build on top.
- Applies to backend RP proposal/apply governance for authoritative Core State targets.
- This slice is a narrow enforcement layer over the existing `ProposalApplyService` and `ProposalRepository` path. It does not create a new workflow, a new revision store, or a public apply tool family.
- Projection mutation, Recall, Archival, and Runtime Workspace promotion remain out of scope.

### 2. Signatures

Existing input model:

```python
class ProposalSubmitInput(BaseModel):
    base_refs: list[ObjectRef] = Field(default_factory=list)
```

Apply service:

```python
class ProposalApplyService:
    def apply_proposal(self, proposal_id: str) -> ProposalReceipt: ...
```

Stable helper direction:

```python
class ProposalApplyService:
    def _validate_base_revisions(
        self,
        *,
        session,
        proposal_record,
        input_model: ProposalSubmitInput,
        target_refs: list[ObjectRef],
    ) -> None: ...
```

### 3. Contracts

#### Base revision contract

- `base_refs` are the authoritative conflict guard for the targets a proposal intends to change.
- For every authoritative target ref in the proposal, if a matching `base_ref` is provided, the current authoritative revision must equal the base revision.
- The first enforcement slice is fail-closed on stale revisions. It must not silently overwrite user edits or newer accepted updates.
- If a matching `base_ref` exists but its revision is missing, the apply must fail rather than guess.
- This slice remains legacy-compatible for proposals that carry no `base_refs`; those proposals keep the current behavior until the later worker/user-edit slices require mandatory base refs.

#### Matching contract

- Matching should be done against the normalized authoritative target ref identity, not against incidental object shapes.
- Each authoritative target in the proposal should resolve to one matching base ref when `base_refs` are present.
- The matching comparison must use the current authoritative revision for that exact target identity and session.

#### Error contract

- Stale revision mismatch should fail with a stable `ValueError` code prefix so proposal status and API surfaces can report it consistently.
- Suggested stable codes:
  - `phase_e_apply_base_revision_missing`
  - `phase_e_apply_base_revision_conflict`
- The error message should include enough target identity detail to explain which object was stale.
- On failure, the proposal status must move to `failed` and no apply receipt should be created.

#### Mutation contract

- Base revision validation must happen before authoritative mutation, before apply receipt creation, and before proposal status is marked `applied`.
- Existing successful apply behavior stays the same for matching revisions.
- Existing idempotent re-apply behavior for already-applied proposals stays intact.
- No direct writes to `StorySession.current_state_json`, Core State tables, or projection mirrors should be introduced by this slice.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Proposal has no `base_refs` | Existing apply behavior continues in this slice |
| Proposal has a `base_ref` whose revision matches current authoritative revision | Apply continues normally |
| Proposal has a `base_ref` whose revision is stale | Fail closed with `phase_e_apply_base_revision_conflict` |
| Proposal has a matching `base_ref` without a revision | Fail closed with `phase_e_apply_base_revision_missing` |
| Proposal applies after a stale base revision failure | Proposal status becomes `failed`; no extra apply receipt is created |
| Already-applied proposal is re-applied | Existing idempotent behavior remains unchanged |

### 5. Good / Base / Bad Cases

- Good: a review-required proposal with `base_refs` matching the current authoritative revisions applies normally and records the next revision.
- Good: a stale worker candidate fails closed before touching memory truth.
- Base: proposals that never supplied `base_refs` still behave like the current legacy path in this slice.
- Bad: silently applying over a newer user edit.
- Bad: auto-merging stale revisions without an explicit safe-merge policy.
- Bad: introducing a parallel revision store or a new direct write path.

### 6. Tests Required

- Positive apply test with matching `base_refs` still passes and produces the expected apply receipt.
- Regression test for stale `base_refs`:
  - a proposal with an older base revision fails closed;
  - proposal status becomes `failed`;
  - no extra apply receipt is created;
  - the authoritative state remains unchanged.
- Optional guard test for a missing base revision on a supplied `base_ref`.
- Existing apply idempotency tests remain green.
- Focused lint/type checks must include the updated apply service and new regression tests.

### 7. Wrong vs Correct

#### Wrong

```python
return self._story_state_apply_service.apply(state_map=before_snapshot, patch=patch)
```

This mutates truth before checking whether the proposal is still based on the current revision.

#### Correct

```python
self._validate_base_revisions(
    session=session,
    proposal_record=proposal_record,
    input_model=input_model,
    target_refs=target_refs,
)
after_snapshot = self._story_state_apply_service.apply(
    state_map=before_snapshot,
    patch=patch,
)
```

The conflict guard runs first, and only a matching base revision may proceed to authoritative mutation.
