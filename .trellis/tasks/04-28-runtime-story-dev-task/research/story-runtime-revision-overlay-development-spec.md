# Story Runtime Revision Overlay Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Longform Revision Overlay / Rewrite / SuperDoc Adapter
>
> Status: development-spec-v1
>
> Canonical requirement spec: [story-runtime-revision-overlay-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-revision-overlay-spec.md)

## 1. Scope / Trigger

This development spec turns the revision overlay requirement spec into an implementation-ready contract.

It is triggered by a cross-layer feature:

- backend runtime records for draft materialization, comments, tracked changes, rewrite requests, selection receipts, and adoption receipts
- writer packet sidecars for `review_overlay_sections`
- frontend document/revision UI with SuperDoc/Word-style `viewing / editing / suggesting`
- rewrite actions that route through the existing `WritingWorker`
- post-write and next-turn behavior that only treats adopted drafts as canonical continuation base

This spec does not replace these canonical specs:

- `WritingPacket / PacketSection / RuntimeReadManifestRecord`: [story-runtime-context-packet-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-context-packet-spec.md)
- `WritingWorkerExecutionRequest / WritingWorkerExecutionResult`: [story-runtime-writing-worker-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-writing-worker-spec.md)
- `Turn / RuntimeWorkspaceMaterial / RuntimeWorkflowJobRecord`: [story-runtime-workspace-ledger-trace-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-workspace-ledger-trace-spec.md)
- post-write settlement and governance: [story-runtime-postwrite-memory-governance-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-postwrite-memory-governance-spec.md)

First implementation goal:

1. Materialize writer markdown/text draft into stable document blocks.
2. Persist review overlay sidecars under the current `Turn`.
3. Support one `full rewrite` action and one `paragraph rewrite` target per request.
4. Preserve rewrite candidates until the user selects and adopts one via `accept_and_continue`.
5. Keep SuperDoc as UI/document substrate, not as runtime truth owner.

Implementation note for SuperDoc integration:

- SuperDoc source/docs may be used to align the UI adapter with its real document mode, comment, tracked-change, selection, and export behavior.
- R2 backend persistence must not depend on SuperDoc as the source of truth. Persist RP runtime DTOs first; store SuperDoc identifiers only as adapter metadata, for example `RevisionAnchorRef.superdoc_anchor_id`.
- Do not add a SuperDoc Python/Node SDK dependency in R2 unless a later slice explicitly needs headless DOCX automation. The first integration target is the visible frontend document/revision substrate and its adapter events.
- If SuperDoc behavior conflicts with this task's PRD/spec/development spec, implement the RP runtime contract and isolate the mismatch in the future SuperDoc adapter layer.

## 2. Signatures

Recommended backend model files:

- `backend/rp/models/revision_overlay_contracts.py`
- `backend/rp/services/draft_materialization_service.py`
- `backend/rp/services/revision_overlay_service.py`
- `backend/rp/services/rewrite_request_builder_service.py`
- `backend/rp/services/draft_selection_service.py`

Recommended frontend surfaces:

- longform draft panel document view
- revision toolbar mode switch: `viewing | editing | suggesting`
- comment / tracked change side panel
- candidate selector
- `accept_and_continue` adoption action

### 2.1 DTOs

```python
class DraftDocumentBlock(BaseModel):
    block_id: str
    order: int
    block_kind: Literal["paragraph", "heading", "list_item", "blockquote", "code", "unknown"]
    text: str
    markdown_source_range: dict[str, int] | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class DraftDocumentRecord(BaseModel):
    draft_document_id: str
    turn_id: str
    draft_ref: str
    source_output_ref: str
    source_format: Literal["markdown", "plain_text"]
    blocks: list[DraftDocumentBlock]
    materialization_version: str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class ReviewOverlayRecord(BaseModel):
    overlay_id: str
    turn_id: str
    draft_ref: str
    draft_document_id: str
    mode: Literal["viewing", "editing", "suggesting"]
    comment_refs: list[str] = Field(default_factory=list)
    tracked_change_refs: list[str] = Field(default_factory=list)
    selection_refs: list[str] = Field(default_factory=list)
    overlay_status: Literal["active", "resolved", "stale", "archived"] = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class RevisionAnchorRef(BaseModel):
    anchor_scope: Literal["inline", "single_block", "multi_block"]
    block_ids: list[str]
    start_offset: int | None = None
    end_offset: int | None = None
    selected_excerpt_hash: str | None = None
    superdoc_anchor_id: str | None = None
```

```python
class RevisionCommentRecord(BaseModel):
    comment_id: str
    turn_id: str
    draft_ref: str
    overlay_id: str
    anchor_ref: RevisionAnchorRef
    selected_excerpt: str | None = None
    instruction_text: str
    status: Literal["active", "resolved", "deleted"] = "active"
    created_by: Literal["user", "system"] = "user"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class TrackedChangeRecord(BaseModel):
    tracked_change_id: str
    turn_id: str
    draft_ref: str
    overlay_id: str
    anchor_ref: RevisionAnchorRef
    change_kind: Literal["insert", "delete", "replace"]
    original_text: str | None = None
    suggested_text: str | None = None
    status: Literal["active", "accepted", "rejected", "deleted"] = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class RewriteRequest(BaseModel):
    request_id: str
    session_id: str
    turn_id: str
    draft_ref: str
    draft_document_id: str
    rewrite_scope: Literal["full", "paragraph"]
    global_instruction: str | None = None
    target_block_ids: list[str] = Field(default_factory=list)
    target_range_ref: dict[str, int] | None = None
    comment_refs: list[str] = Field(default_factory=list)
    tracked_change_refs: list[str] = Field(default_factory=list)
    include_full_draft_text: bool
    full_draft_text: str | None = None
    anchor_refs: list[RevisionAnchorRef] = Field(default_factory=list)
    comments: list[RevisionCommentRecord] = Field(default_factory=list)
    tracked_changes: list[TrackedChangeRecord] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class ParagraphRewritePatch(BaseModel):
    draft_ref: str
    target_block_ids: list[str]
    replacement_blocks: list[ReplacementBlock]
    touched_comment_ids: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

class ReplacementBlock(BaseModel):
    block_id: str
    replacement_text: str
    order: int
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class LongformDraftSelectionReceipt(BaseModel):
    receipt_id: str
    turn_id: str
    candidate_output_refs: list[str]
    selected_output_ref: str
    selection_source: Literal["user_explicit_select"]
    selected_at: datetime
    cleared_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class LongformDraftAdoptionReceipt(BaseModel):
    receipt_id: str
    turn_id: str
    adopted_output_ref: str
    adoption_source: Literal["accept_and_continue"]
    adopted_at: datetime
    selection_receipt_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

### 2.2 Service Surface

```python
class DraftMaterializationService:
    def materialize_draft(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str,
        output_text: str,
        source_format: Literal["markdown", "plain_text"],
    ) -> DraftDocumentRecord: ...
```

```python
class RevisionOverlayService:
    def create_or_update_overlay(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_document_id: str,
        mode: Literal["viewing", "editing", "suggesting"],
    ) -> ReviewOverlayRecord: ...

    def add_comment(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        overlay_id: str,
        anchor_ref: RevisionAnchorRef,
        instruction_text: str,
        selected_excerpt: str | None = None,
    ) -> RevisionCommentRecord: ...

    def add_tracked_change(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        overlay_id: str,
        anchor_ref: RevisionAnchorRef,
        change_kind: Literal["insert", "delete", "replace"],
        original_text: str | None = None,
        suggested_text: str | None = None,
    ) -> TrackedChangeRecord: ...

    def resolve_comment(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        comment_id: str,
    ) -> RevisionCommentRecord: ...

    def delete_comment(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        comment_id: str,
    ) -> RevisionCommentRecord: ...
```

```python
class RewriteRequestBuilderService:
    def build_full_rewrite_request(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str,
        global_instruction: str | None,
        comment_refs: list[str],
        tracked_change_refs: list[str],
    ) -> RewriteRequest: ...

    def build_paragraph_rewrite_request(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str,
        target_block_ids: list[str],
        comment_refs: list[str],
        tracked_change_refs: list[str],
        global_instruction: str | None = None,
    ) -> RewriteRequest: ...
```

```python
class DraftSelectionService:
    def select_candidate(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        turn_id: str,
        candidate_output_refs: list[str],
        selected_output_ref: str,
    ) -> LongformDraftSelectionReceipt: ...

    def clear_selection(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        turn_id: str,
    ) -> LongformDraftSelectionReceipt | None: ...

    def adopt_for_continue(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        turn_id: str,
        selected_output_ref: str | None = None,
    ) -> LongformDraftAdoptionReceipt: ...
```

## 3. Contracts

### 3.1 Draft Materialization

`DraftMaterializationService` is the only component allowed to convert writer raw content into revision blocks.

Rules:

- Writer may output markdown or plain text.
- Runtime must not use raw `"\n"` splitting as canonical anchor semantics.
- Markdown parsing may produce a first-pass block sequence.
- Stable `block_id` should be derived from `draft_ref + block order + normalized block text hash`.
- If text changes and hash stability is not enough, implementation must retain `selected_excerpt` and offsets as fallback anchors.
- The frontend may render markdown styles, but revision anchors bind to `DraftDocumentBlock` or `RevisionAnchorRef`, not to rendered DOM nodes alone.

### 3.2 SuperDoc Boundary

SuperDoc can own:

- document editing surface
- block/node/range selection UI
- comments UI
- tracked changes UI
- accept/reject/resolve interaction vocabulary

SuperDoc cannot own:

- `Turn`
- `draft_ref`
- `candidate_output_ref`
- rewrite packet semantics
- draft selection/adoption
- post-write settlement
- Core State / Recall / Archival truth

Runtime stores SuperDoc ids only as adapter metadata such as `superdoc_anchor_id`.

### 3.3 Review Overlay

Review overlay is current-turn material.

It is not:

- canonical story text
- Core State truth
- Recall memory
- a separate product timeline

It is:

- sidecar material for rewrite packet
- provenance for debug / rollback / export
- user-visible review state

Implementation invariants:

- Runtime Workspace material ids for draft documents, overlays, comments, tracked changes, rewrite candidates, selection receipts, and adoption receipts must be scoped by the full `MemoryRuntimeIdentity`. Stable document ids such as `draft_document_id` are not sufficient as persistent material keys because the same draft text can exist on different branches.
- Review overlay sidecars may store deterministic `record_id` values for lookup, but the persisted material key must prevent cross-story, cross-session, cross-branch, cross-turn, and cross-runtime-profile collisions.
- Read/ensure surfaces such as `read_revision_review_surface` may materialize the current draft document and ensure an overlay exists, but the same identity + same draft document + same mode read must be idempotent. Re-reading must reuse the existing draft material and overlay instead of creating a new Runtime Workspace sidecar version.

### 3.4 Full Rewrite

There is one `full rewrite` product action with two input shapes:

| Condition | Include old full draft text | Required payload |
|---|---:|---|
| only full-document comments/tracked changes, no explicit global instruction | yes | full draft text + comments / tracked changes |
| explicit global instruction exists | no | instruction + outline/goal/core/recent refs |

The service must not infer "many paragraph comments means full rewrite". That upgrade is explicitly out of scope.

If no explicit `global_instruction` exists, old full draft text is required. The implementation must reject an explicit attempt to disable full draft text for this comments-only full rewrite shape.

### 3.5 Paragraph Rewrite

Paragraph rewrite is one target per request.

Rules:

- `target_block_ids` is required and non-empty.
- All referenced comments/tracked changes must anchor inside `target_block_ids` or explicitly mark themselves as whole-draft context.
- Writer may receive full draft text as background.
- Writer output must be patch-shaped: `replacement_blocks`, not only free whole-draft text.
- Deterministic composer applies `replacement_blocks` to produce a new candidate draft.
- The new candidate is not adopted automatically.

### 3.6 Selection vs Adoption

Selection is reversible state.

Adoption is a committed runtime receipt.

Rules:

- If a turn has exactly one candidate, `accept_and_continue` may adopt it without a prior selection receipt.
- If a turn has multiple candidates, `accept_and_continue` requires an active selection receipt or explicit `selected_output_ref`.
- Selection can be cleared or changed before adoption.
- Adoption occurs only at `accept_and_continue`.
- Next-turn writer packet and post-write governance use the adopted output, not the merely selected output.

### 3.7 Comment Lifecycle

Rules:

- New comments default to `active`.
- Rewrite never auto-resolves comments.
- User explicitly chooses `resolve`, keep active, or delete.
- Resolved comments are hidden from the main review working view by default but remain in provenance/debug/export surfaces.
- Deleted comments remain as tombstones if needed for audit; they must not enter future rewrite packets.

### 3.8 WritingPacket Sidecar

Revision data enters writer through `review_overlay_sections`.

Minimum sidecar fields:

- `draft_ref`
- `draft_document_id`
- `rewrite_scope`
- `target_block_ids`
- `comments`
- `tracked_changes`
- `selected_excerpt`
- `anchor_refs`
- `instruction_text`
- `include_full_draft_text`
- `source_ref_ids`

The revision module must not add arbitrary top-level packet fields outside the context-packet contract. If additional metadata is needed, put it under packet metadata or sidecar payload.

Implementation note:

- The rewrite request builder may carry a richer internal `RewriteRequest` payload than the minimum packet sidecar fields, so it can deterministically derive `review_overlay_sections` without re-querying unrelated state.
- In R3, paragraph rewrite validation still stays request-side: one contiguous target scope per request, active comment/tracked change refs only, and full-draft text only when the request shape allows it.
- Internal rewrite request and candidate records must carry and validate the full runtime identity metadata (`story_id`, `session_id`, `branch_head_id`, `turn_id`, `runtime_profile_snapshot_id`). Later services must fail closed if a request lacks this metadata or if it does not match the active identity.

### 3.9 Selection / Adoption Trace

Selection and adoption receipts are Runtime Workspace sidecars, not Core/Recall/Archival truth.

Rules:

- Adoption receipts created from an active selection must include that selection receipt in their source refs.
- Adoption receipts may mark `canonical_continuation_base=True` for next-turn anchoring, but they still must keep `canonical_truth=False` and must not write Core State / Recall / Archival truth directly.
- Next-turn adopted output anchors must be derived from the adoption receipt, not from the current active selection.

## 4. Validation & Error Matrix

| Condition | Error code | Behavior |
|---|---|---|
| `identity.turn_id` does not match overlay/comment turn | `revision_turn_mismatch` | reject request |
| draft not found or not visible on active branch | `revision_draft_not_visible` | reject request |
| comment references missing draft | `revision_comment_draft_mismatch` | reject request |
| `suggesting` action attempts direct canonical text update | `revision_suggesting_not_canonical_write` | reject request |
| `editing` action tries to create LLM rewrite instruction automatically | `revision_editing_not_rewrite_instruction` | store edit candidate only |
| paragraph rewrite without `target_block_ids` | `revision_target_blocks_required` | reject request |
| paragraph rewrite references multiple disconnected targets | `revision_batch_paragraph_rewrite_unsupported` | reject request |
| paragraph rewrite output lacks `replacement_blocks` | `revision_replacement_blocks_required` | reject or repair before persistence |
| full rewrite with explicit global instruction includes old full draft text | `revision_full_rewrite_old_text_forbidden` | reject or rebuild packet without old text |
| full rewrite without explicit global instruction omits old full draft text | `revision_full_rewrite_old_text_required` | reject request |
| rewrite request missing full runtime identity metadata | `revision_runtime_identity_missing` | reject request/candidate |
| rewrite request identity metadata does not match active identity | `revision_<identity_field>_mismatch` | reject request/candidate |
| multiple candidates and no selected output on continue | `revision_adoption_selection_required` | block `accept_and_continue` |
| selected output not in candidate refs | `revision_selected_output_not_candidate` | reject request |
| rewrite attempts to auto-resolve comment | `revision_comment_auto_resolve_forbidden` | keep comment active |

## 5. Good / Base / Bad Cases

Good:

- User enters `suggesting`, selects one paragraph, adds a comment, triggers paragraph rewrite, writer returns `replacement_blocks`, runtime creates a new candidate, original comment remains active.

Base:

- User has one generated draft and clicks `accept_and_continue`; runtime creates adoption receipt for the only candidate and continues.

Bad:

- User has three rewrite candidates and clicks `accept_and_continue` without choosing. Runtime must reject with `revision_adoption_selection_required`.

Bad:

- Full rewrite with explicit "make this more intimate and slower" instruction also includes old full draft text. Runtime must not send the old full draft text in this shape.

Bad:

- Paragraph rewrite returns one full free-text article without `target_block_ids` mapping. Runtime must not apply it as a deterministic patch.

## 6. Tests Required

Backend unit tests:

1. `DraftMaterializationService` creates stable block ids for unchanged markdown.
2. Comments/tracked changes reject anchors outside the current draft document.
3. `editing` does not create review overlay instructions.
4. `suggesting` creates overlay sidecars.
5. Full rewrite packet includes old draft text only in the "comments only, no global instruction" shape.
6. Full rewrite packet excludes old draft text when `global_instruction` exists.
7. Paragraph rewrite requires exactly one target scope and emits patch-shaped output.
8. Rewrite candidate does not set adopted/canonical output.
9. Selection receipt can be changed before adoption.
10. Multiple candidates require selection before `accept_and_continue`.
11. Adoption receipt is created only during `accept_and_continue`.
12. Rewrite does not auto-resolve comments.
13. Review overlay material keys remain isolated when two branches materialize the same stable draft document id.
14. Rewrite request/candidate services reject stale or cross-branch runtime identity metadata.
15. Adoption receipt source refs include the active selection receipt when adoption uses a prior selection.
16. Repeated revision review surface reads for the same identity/draft/mode do not create duplicate draft/overlay sidecar versions.

Backend integration tests:

1. Generate longform draft -> materialize document -> add comment -> paragraph rewrite -> candidate created -> old comment active.
2. Generate draft -> full rewrite -> choose candidate -> accept_and_continue -> next writer packet uses adopted output.
3. Branch switch after fork does not expose another branch's pending review overlay or candidate drafts.
4. Runtime inspect/debug surfaces expose overlay, comment, selection, adoption refs as turn materials, not truth.

Frontend tests:

1. `viewing` mode prevents edit/comment commands.
2. `editing` mode updates draft candidate but does not create LLM rewrite instruction.
3. `suggesting` mode creates comment/tracked-change sidecar.
4. Candidate selector shows all candidates and keeps current selection reversible.
5. `accept_and_continue` is disabled for multiple candidates without selection.
6. Resolved comments are hidden from main review view but available in history/debug view.

## 7. Wrong vs Correct

### Wrong: raw newline anchors

```python
block_id = f"paragraph:{line_number}"
```

This breaks when markdown headings, lists, wrapped text, or edits change newline positions.

### Correct: materialized document block anchor

```python
block_id = stable_block_id(
    draft_ref=draft_ref,
    order=block_order,
    normalized_text=normalize_block_text(block.text),
)
```

The block id can still change after heavy edits, so comments must also keep selected excerpt and optional source range fallback.

### Wrong: rewrite auto-adopts latest output

```python
result.selected_output_ref = result.candidate_output_ref
```

### Correct: rewrite creates candidate only

```python
result.candidate_output_ref = candidate_ref
result.selected_output_ref = None
```

Adoption is handled later by `DraftSelectionService.adopt_for_continue()`.

### Wrong: SuperDoc owns runtime truth

```python
canonical_output_ref = superdoc_document.current_revision_id
```

### Correct: SuperDoc id is adapter metadata

```python
comment.anchor_ref.superdoc_anchor_id = superdoc_anchor_id
canonical_output_ref = adoption_receipt.adopted_output_ref
```

## 8. Implementation Slices

### Slice R1: Draft Materialization / Anchor Contract

Owner scope:

- backend DTOs
- materialization service
- tests for block stability and anchor fallback

Do not implement SuperDoc UI in this slice.

### Slice R2: Review Overlay Persistence

Owner scope:

- review overlay records
- comments
- tracked changes
- resolve/delete lifecycle
- read-only inspect/debug exposure

Do not trigger rewrite from this slice.

### Slice R3: Rewrite Request / Packet Sidecar

Owner scope:

- full rewrite request builder
- paragraph rewrite request builder
- `review_overlay_sections` mapping into writer packet
- validation matrix

Do not create separate rewrite worker.

### Slice R4: Rewrite Candidate / Patch Composer

Owner scope:

- paragraph `replacement_blocks`
- full rewrite candidate output
- candidate list visibility
- no auto-adoption enforcement

Do not implement multi-target paragraph rewrite.

### Slice R5: Selection / Adoption / Continue

Owner scope:

- selection receipt
- adoption receipt
- `accept_and_continue` gating
- next-turn adopted output anchor

Do not treat mere selection as post-write canonical truth.

### Slice R6: Minimal Frontend Review Surface

Owner scope:

- lightweight SuperDoc/Word-style document view
- mode switch `viewing / editing / suggesting`
- comment/tracked-change controls
- candidate selector
- accept/resolve/delete actions

Do not build rich formatting toolbar, complex tree diff UI, or batch rewrite UI.

## 9. Parallelization Guidance

R1 must finish before R2/R3.

R2 and R3 can proceed in parallel only if they do not modify the same files and both consume frozen DTOs from R1.

R4 depends on R3.

R5 depends on R4 and the current longform accept/continue command surface.

R6 can start after R1/R2 DTOs are frozen, but must not define backend truth from UI state.

Module-level `trellis-check` should run after R1-R5 backend contract is complete, and a second check should run after R6 if frontend is included.

## 10. Out of Scope

- batch paragraph rewrite
- automatic upgrade from many local comments to full rewrite
- comment auto-resolve after rewrite
- rich text formatting as product capability
- complex branch diff UI
- SuperDoc as persisted truth owner
- separate rewrite worker
- roleplay / TRPG candidate tree

## 11. Future Migration Notes

Setup-stage draft manual editing should reuse the same overlay/adoption vocabulary where practical, but it must bind to setup draft identity instead of story `Turn`.

Roleplay / TRPG should not use longform multi-candidate adoption. Their dissatisfaction path is branch/rollback from historical `Turn`, not in-turn candidate selection.
