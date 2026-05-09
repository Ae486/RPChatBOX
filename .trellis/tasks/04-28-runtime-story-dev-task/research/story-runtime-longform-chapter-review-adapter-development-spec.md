# Story Runtime Longform Chapter / Review Adapter Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Longform Chapter Lifecycle / Review Adapter
>
> Status: development-spec-v1

## 1. Scope

This spec plans the next longform-focused runtime layer after the first-stage minimal loop and revision overlay.

It covers:

- chapter lifecycle provider boundaries;
- chapter bridge material between completed and next chapters;
- discussion / review / rewrite / accept-and-continue alignment;
- adapter rules for old longform MVP surfaces;
- minimal tests proving chapter progression uses adopted draft content.

It does not cover:

- full rich text editor;
- SuperDoc as backend truth;
- complete branch tree UI;
- roleplay/TRPG candidate or branch products.

## 2. Frozen Flow

```text
chapter start
  -> accepted outline / chapter goal / chapter bridge material
  -> user discussion or confirmation
  -> writing / rewrite
  -> accept_and_continue or complete_chapter
  -> chapter close maintenance
  -> next chapter preparation
```

Longform output remains draft-first.

- `WritingWorker` creates candidate draft artifacts.
- `review overlay` stores comments/tracked changes.
- `rewrite` creates new candidates.
- `selection` is reversible.
- `accept_and_continue` creates adoption receipt.
- Only adopted output becomes canonical continuation base.

## 3. Suggested Files

Backend:

- `backend/rp/models/longform_chapter_contracts.py`
- `backend/rp/services/chapter_bridge_provider.py`
- `backend/rp/services/longform_chapter_runtime_service.py`
- `backend/rp/services/story_turn_domain_service.py`
- `backend/rp/services/draft_selection_service.py`

Frontend:

- existing longform page
- chapter status panel
- candidate/revision surface already introduced by R module

Tests:

- `backend/rp/tests/test_longform_chapter_runtime_service.py`
- existing draft selection and story API tests

## 4. DTOs

```python
class ChapterBridgeMaterial(BaseModel):
    bridge_id: str
    session_id: str
    branch_head_id: str
    source_chapter_index: int
    target_chapter_index: int
    accepted_outline_ref: str | None = None
    chapter_goal_ref: str | None = None
    continuity_refs: list[str] = Field(default_factory=list)
    summary_text: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class LongformChapterTransitionReceipt(BaseModel):
    receipt_id: str
    identity: MemoryRuntimeIdentity
    from_chapter_index: int
    to_chapter_index: int
    adopted_output_ref: str | None = None
    bridge_material_ref: str | None = None
    status: Literal["prepared", "completed", "blocked"]
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

## 5. Provider Contract

```python
class ChapterBridgeProvider:
    def build_bridge_material(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        from_chapter_index: int,
        to_chapter_index: int,
        adopted_output_ref: str | None,
    ) -> ChapterBridgeMaterial: ...
```

First provider behavior:

- include accepted outline;
- include chapter goal;
- include adopted output ref when available;
- do not invent a heavy compact summary unless a later eval-backed provider requires it.

Provider replacement is allowed through registry/config later. The main chapter flow must not hardcode a specific summarization implementation.

## 6. Adapter Rules

Old longform MVP surfaces may be adapted only when they map cleanly to the new contracts.

Allowed:

- reuse existing page layout;
- reuse old command names as compatibility shell if they call new services;
- read legacy chapter workspace mirrors through explicit adapter.

Forbidden:

- old command surface defining backend truth;
- rewrite immediately superseding/adopting latest candidate;
- chapter progression reading unadopted draft;
- discussion output becoming canonical prose without adoption.

## 7. State Rules

- `complete_chapter` is a deterministic turn/action that closes the current chapter line.
- It must use the adopted draft output, not the latest candidate.
- If no adopted draft exists and completion requires prose, reject or require explicit adoption.
- Chapter bridge material is Runtime Workspace / chapter sidecar material, not Core truth by itself.
- Post-write governance may later materialize chapter summaries into Recall/Core through existing governed paths.
- `complete_chapter` may keep a compatibility path for already accepted legacy segments when no pending rewrite candidate exists.
- If pending rewrite candidates exist, `complete_chapter` must fail closed until an adoption receipt identifies the canonical continuation base.
- `ChapterBridgeProvider` must record bridge material under full runtime identity and current branch.
- The next chapter writer packet must read the latest bridge only by current `story_id / session_id / branch_head_id / target_chapter_index`.
- Other branches' bridge material must not leak into the active branch packet.
- Packet injection may include bridge summary, current chapter goal, accepted outline ref, and continuity refs; it must not promote Runtime Workspace sidecar material into chapter truth.

## 8. Tests Required

1. `accept_and_continue` adoption is the only continuation base for next write.
2. `complete_chapter` rejects ambiguous multiple candidates without adoption.
3. Chapter bridge provider receives adopted output ref, not selected/unadopted candidate.
4. Discussion summary does not become prose continuation base unless explicitly applied through the correct flow.
5. Legacy adapter route returns the same canonical chapter state as new read surface.
6. Branch switch does not expose another branch's chapter bridge or pending revision state.
7. Next chapter writer packet receives the current branch's `chapter_bridge_material`.
8. Next chapter writer packet does not receive bridge material from a sibling branch.

## 9. Out of Scope

- Heavy chapter compaction provider.
- Full review/export UI.
- Auto-resolving comments on chapter complete.
- Cross-branch chapter merge.
- Treating bridge sidecar as Core / Recall / Archival truth.
