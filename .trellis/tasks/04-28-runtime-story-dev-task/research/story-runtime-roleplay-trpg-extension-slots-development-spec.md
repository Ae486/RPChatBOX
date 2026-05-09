# Story Runtime Roleplay / TRPG Extension Slots Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Roleplay / TRPG Extension Slots
>
> Status: development-spec-v1

## 1. Scope

This spec freezes extension slots that prevent the runtime from becoming longform-only.

It covers:

- mode/profile extension points for roleplay and TRPG;
- worker catalog placeholders;
- Runtime Workspace sidecar material types;
- writer acceptance semantics for interactive modes;
- tests proving extension slots can mount without rewriting the longform writer core.

It does not implement:

- complete roleplay character simulation;
- complete TRPG rule engine;
- full message tree UI;
- same-turn candidate tree for roleplay/TRPG.

## 2. Design Rules

Roleplay/TRPG share the same runtime skeleton:

- `StorySession`
- `BranchHead`
- `Turn`
- `RuntimeProfileSnapshot`
- `Runtime Workspace`
- worker registry / scheduler
- Context Orchestration Layer
- `WritingWorker`
- post-write governance

They differ through `ModeProfile` and compiled snapshot policy, not separate hardcoded chains.

RP/TRPG do not use longform multi-candidate adoption.

- One `Turn` has one current visible result.
- If the user dislikes the future, they use rollback or branch from a settled turn.
- The next user message is the first-stage acceptance signal for the previous visible response.

## 3. Required Extension Slots

Roleplay:

- `CharacterMemoryWorker`
- `SceneInteractionWorker`
- character-local memory sidecar
- knowledge-boundary refs
- scene intent / participant intent sidecars

TRPG:

- `RuleStateWorker`
- `RULE_CARD`
- `RULE_STATE_CARD`
- mechanics state refs
- rule adjudication trace

Shared:

- branch-aware Runtime Workspace materials;
- post-write background preparation;
- writer packet sidecar family;
- mode-specific knowledge-gap policy.

## 4. Suggested Files

Backend:

- `backend/rp/models/mode_extension_contracts.py`
- `backend/rp/models/runtime_workspace_material.py`
- `backend/rp/services/story_worker_registry_service.py`
- `backend/rp/services/worker_scheduler_service.py`
- `backend/rp/services/context_orchestration_service.py`
- `backend/rp/services/story_runtime_workspace_facade.py`

Tests:

- `backend/rp/tests/test_mode_extension_slots.py`
- worker registry / scheduler tests
- Runtime Workspace material tests

## 5. DTOs

```python
class RuntimeModeExtensionSlot(BaseModel):
    mode: Literal["longform", "roleplay", "trpg"]
    slot_id: str
    slot_kind: Literal["worker", "workspace_material", "packet_sidecar", "policy"]
    descriptor_ref: str
    enabled_by_default: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class RuleCardMaterial(BaseModel):
    material_id: str
    identity: MemoryRuntimeIdentity
    rule_refs: list[str] = Field(default_factory=list)
    adjudication_summary: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

```python
class RuleStateCardMaterial(BaseModel):
    material_id: str
    identity: MemoryRuntimeIdentity
    mechanics_state_patch: dict[str, Any] = Field(default_factory=dict)
    status_effects: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

## 6. Worker Placeholders

The first extension implementation may register descriptors without full LLM behavior.

Required descriptor behavior:

- worker id is registry-discovered;
- worker domain bindings come from compiled snapshot;
- scheduler can select/skip/degrade the worker without mode-specific `if` chains;
- worker output can be represented as `WorkerResult`;
- missing executor fails/degrades with trace rather than crashing the turn.
- placeholder descriptors are allowed in O1, but they must still compile through the same `RuntimeProfileSnapshot` path as real workers.
- extension workers must not be discovered through a separate roleplay/TRPG runtime registry.

## 7. Runtime Workspace Material Rules

Roleplay/TRPG sidecars are turn materials.

They are not:

- Core truth;
- Recall history;
- Archival source material;
- longform draft candidates.

They may later become source refs for governed Core proposals, Recall materialization, or Archival evolution, but only through post-write governance.

Implementation rules:

- `RULE_CARD` and `RULE_STATE_CARD` must persist as formal Runtime Workspace materials with `source_refs`, not only payload-local provenance.
- sidecar lookup must remain full-identity and branch-scoped.
- sidecars may be exposed to packets through mode sidecar sections or worker sidecar refs, but they must not add arbitrary top-level packet fields.
- `WorkerContextPacket.sidecar_refs` must honor requested `context_requirements.sidecar_slot_ids`; enabling a sidecar in a mode profile is not enough to expose it to every worker packet.
- When no `context_requirements.sidecar_slot_ids` are explicitly requested, worker packet sidecar refs must stay empty.
- `RULE_CARD` and `RULE_STATE_CARD` must not enter a worker packet through generic `workspace_refs` as a bypass around sidecar-slot filtering.
- Packet/debug surfaces must identify mode sidecar sections through stable metadata such as `section_family=mode_sidecar`, not by parsing display labels.

## 8. Acceptance / Settlement

For roleplay/TRPG:

- writer output is visible immediately;
- previous output becomes accepted when the user sends the next message, unless the user explicitly rolls back/branches before continuing;
- a failed required TRPG rule/state post-write task may gate continuation if the failure affects hard mechanics;
- roleplay can continue with pending-deferred state when mode policy allows, using the last stable prepared view.

## 9. Tests Required

1. Roleplay profile can compile with `CharacterMemoryWorker` and `SceneInteractionWorker` descriptors without scheduler code changes.
2. TRPG profile can compile with `RuleStateWorker`, `RULE_CARD`, and `RULE_STATE_CARD` material slots.
3. Scheduler can skip/degrade a registered extension worker with missing executor and preserve trace.
4. Runtime Workspace stores rule card/state card as branch-scoped turn materials and does not promote them to truth.
5. Context packet builder can include mode sidecars through packet policy without new top-level packet fields.
6. Roleplay/TRPG turn acceptance uses next user message and does not create longform adoption receipts.
7. Branch/rollback hides extension sidecars after the rollback cutoff.
8. Worker packet sidecar refs are filtered by requested sidecar slot ids.
9. Rule card/state card formal Runtime Workspace `source_refs` are persisted and visible to trace/debug reads.
10. Worker packet without requested sidecar slot ids exposes no rule-card sidecar refs.
11. Rule card/state card cannot leak through generic `workspace_refs`.

## 10. Out of Scope

- Complete character simulation prompts.
- Complete rule adjudication engine.
- Dice/initiative/combat state UI.
- RP/TRPG same-turn candidate switching.
- Heavy branch tree visualization.
