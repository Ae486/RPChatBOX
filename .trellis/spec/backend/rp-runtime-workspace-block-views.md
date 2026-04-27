# RP Runtime Workspace Block Views

## Scenario: Active-story Runtime Workspace surfaces expose read-only Block views

### 1. Scope / Trigger

- Trigger: Phase D3 of the Memory OS Block rollout needs the remaining uncovered memory layer, `Runtime Workspace`, to participate in the Block-facing read model.
- Applies to:
  - `RpBlockReadService`
  - `StoryRuntimeController`
  - `/api/rp/story-sessions/{session_id}/memory/blocks*`
  - focused backend tests for read-side behavior
- This slice is additive and read-only. It does not create durable truth, history, provenance, or mutation semantics for runtime workspace objects.

### 2. Signatures

Shared source enum:

```python
BlockSource = Literal[
    "core_state_store",
    "compatibility_mirror",
    "retrieval_store",
    "runtime_workspace_store",
]
```

Read entry:

```python
class RpBlockReadService:
    def list_blocks(
        self,
        *,
        session_id: str,
        layer: Layer | None = None,
        source: BlockSource | None = None,
    ) -> list[RpBlockView]: ...
```

Runtime Workspace Block identity:

- draft artifact block id: `runtime_workspace:artifact:{artifact_id}`
- discussion entry block id: `runtime_workspace:discussion:{entry_id}`

### 3. Contracts

- Runtime Workspace Block views are read-only, session-scoped views over the **current chapter** runtime objects.
- Treat these views as runtime-scoped surfaces even though the current MVP persists artifacts and discussion entries in database tables.
- Runtime Workspace blocks must use:
  - `layer=Layer.RUNTIME_WORKSPACE`
  - `source="runtime_workspace_store"`
  - `domain=Domain.CHAPTER`
  - `scope="chapter"`
- Draft artifact coverage is limited to `StoryArtifact.status == draft`.
- Accepted or superseded artifacts must stay out of Runtime Workspace Block views for this slice because they represent promoted or historical material, not current-turn scratch state.
- Discussion entry coverage includes current-chapter `StoryDiscussionEntry` rows.
- `label` and `domain_path` must be deterministic, namespaced, and exact-object scoped:
  - `runtime_workspace.artifact.{artifact_id}`
  - `runtime_workspace.discussion.{entry_id}`
- `data_json` must keep the raw runtime object readable without prompt rendering:
  - artifact: full artifact model dump
  - discussion entry: full discussion-entry model dump
- `metadata` must preserve route/source/session/chapter identity and include the backing runtime row id.

Read-side compatibility rules:

- `/memory/blocks` and `/memory/blocks/{block_id}` must include Runtime Workspace Block views beside the existing Core State Block views.
- `layer` and `source` filters must work for Runtime Workspace the same way they already work for Core State.
- `/memory/blocks/{block_id}/versions` and `/memory/blocks/{block_id}/provenance` must stay unsupported for Runtime Workspace and return the existing `memory_block_history_unsupported` error path.
- `/memory/blocks/{block_id}/proposals` must return an empty list for Runtime Workspace blocks.

### 4. Boundary Rules

- Do not promote Runtime Workspace objects into durable Core State truth in this slice.
- Do not attach Runtime Workspace Block views into `StoryBlockConsumerStateService`.
- Do not let Runtime Workspace Block views enter active-story orchestrator/specialist prompt compile attachments; those remain Core State-only.
- Do not expose Runtime Workspace through new public memory tool names.
- Do not create a universal durable Block registry or new `rp_blocks` store.
- Do not let Runtime Workspace Block views replace retrieval payloads, writer packets, or active-story Core State `block_context`.

### 5. Tests Required

- `RpBlockReadService` lists Runtime Workspace blocks for current-chapter draft artifacts and discussion entries.
- Accepted or superseded artifacts are excluded from Runtime Workspace Block views.
- `layer=runtime_workspace` and `source=runtime_workspace_store` filters behave correctly.
- Controller/API list and get routes serialize Runtime Workspace Block views correctly.
- Runtime Workspace `/proposals` returns `[]`.
- Runtime Workspace `/versions` and `/provenance` return `memory_block_history_unsupported`.

### 6. Wrong vs Correct

#### Wrong

```python
# Wrong: accepted artifacts are already promoted or historical, but this
# exposes them as if they were current-turn runtime scratch state.
runtime_blocks = [
    build_runtime_block(artifact)
    for artifact in story_session_service.list_artifacts(...)
]
```

#### Correct

```python
# Correct: keep Runtime Workspace scoped to current-turn draft/discussion
# material and leave promoted history out of the runtime layer.
runtime_blocks = [
    build_runtime_block(artifact)
    for artifact in story_session_service.list_artifacts(...)
    if artifact.status == StoryArtifactStatus.DRAFT
]
```
