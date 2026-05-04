# RP Memory Contract Registry Identity Event Skeleton

## Scenario: First contract slice before story-runtime workers depend on Memory OS

### 1. Scope / Trigger

- Trigger: story runtime needs memory strengthening before worker orchestration, writer-side retrieval, branch/rollback handling, or user-edit conflict handling can safely build on top of the current longform MVP memory surface.
- Applies to backend RP Memory OS contract work for:
  - domain / block registry vocabulary;
  - story-runtime memory identity;
  - lightweight memory change event records;
  - focused model/service tests.
- This is the first strengthening slice. It must not implement full Runtime Workspace turn-material storage, worker-facing public tools, branch UI, proposal/apply rewrite, or a universal durable `rp_blocks` table.

### 2. Signatures

Bootstrap domain ids:

```text
scene
character
knowledge_boundary
relation
goal
timeline
plot_thread
foreshadow
world_rule
inventory
rule_state
chapter
narrative_progress
```

Registry service surface:

```python
class MemoryContractRegistryService:
    def registry_version(self) -> str: ...
    def list_domains(self, *, mode: str | None = None, include_hidden: bool = False) -> list[MemoryDomainContract]: ...
    def get_domain(self, domain_id: str) -> MemoryDomainContract | None: ...
    def require_domain(self, domain_id: str) -> MemoryDomainContract: ...
    def resolve_alias(self, domain_id: str) -> str: ...
    def list_block_templates(self, *, domain_id: str | None = None, layer: str | None = None) -> list[MemoryBlockTemplate]: ...
```

Runtime identity:

```python
class MemoryRuntimeIdentity(BaseModel):
    story_id: str
    session_id: str
    branch_head_id: str
    turn_id: str
    runtime_profile_snapshot_id: str
```

Lightweight event:

```python
class MemoryChangeEvent(BaseModel):
    event_id: str
    identity: MemoryRuntimeIdentity
    actor: str
    event_kind: str
    layer: str
    domain: str
    block_id: str | None
    entry_id: str | None
    operation_kind: str
    source_refs: list[MemorySourceRef]
    dirty_targets: list[MemoryDirtyTarget]
    visibility_effect: str
    metadata: dict[str, Any]
```

### 3. Contracts

#### Registry ownership

- The registry is the source of Memory OS domain / block vocabulary for new story-runtime work.
- The first version is declarative and versioned. It is not full user-editable CRUD.
- The registry must support lifecycle states:
  - `active`
  - `hidden`
  - `retired`
  - `migrated`
- The registry must support aliases / migration ids so a later rename can preserve old records.
- The registry must express mode defaults for at least `longform`, `roleplay`, and `trpg`.
- The registry must express default permission metadata, UI visibility defaults, allowed layers, and block templates.
- For bootstrap domains, `allowed_layers` and active block templates must stay aligned. If a domain declares Core State, Recall, Archival, or Runtime Workspace as an allowed layer, the default registry must expose at least one matching active template for that layer.
- Recall and Archival templates in this first slice are retrieval-backed read templates. They must not inherit proposal/write defaults from authoritative Core State templates.
- Existing typed DTO enums may mirror the current bootstrap set for compatibility, but new services should resolve registry contracts instead of introducing scattered local allowlists.

#### Domain bootstrap contract

- `knowledge_boundary` and `rule_state` are first-class domains, not comments under character/world-rule memory.
- Mode activation defaults may differ:
  - longform can activate `chapter`, `narrative_progress`, `timeline`, `plot_thread`, `foreshadow`, `character`, `scene`, and `knowledge_boundary`;
  - roleplay should activate scene / character / knowledge / relation / goal centered domains;
  - trpg should activate `rule_state`, `inventory`, `world_rule`, scene / character / goal, and knowledge domains.
- Adding a new domain or block in tests must require creating a registry entry, not editing unrelated read services.

#### Identity spine

- Every future memory read / write / proposal / retrieval material must be able to carry:

```text
StorySession + BranchHead + Turn + RuntimeProfileSnapshot
```

- External API routes may still enter through `session_id`.
- The internal contract must distinguish missing identity fields from explicit default values.
- The first slice may provide the identity DTO and resolver skeleton without wiring every existing memory operation.
- Follow-up slices must not create new memory records that only carry `session_id` when the work is branch/turn scoped.

#### Event skeleton

- Add lightweight event models now, not full event sourcing.
- Current truth still lives in Core State, Recall, Archival, and Runtime Workspace stores.
- The event record exists for trace, invalidation, rollback visibility, worker dirty checks, packet/window recompute, and UI audit.
- The event must record actor, layer, session/branch/turn lineage, affected domain/block/refs, operation kind, source refs, downstream invalidation, dirty targets, and visibility effect.
- Candidate events may be represented, but this slice does not require durable candidate persistence.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Default registry is loaded | Returns versioned registry with all 13 bootstrap domains |
| `knowledge_boundary` is requested | Resolves as an active first-class domain |
| `rule_state` is requested | Resolves as an active first-class domain |
| Unknown domain is required | Raises a stable registry error |
| Hidden domain listed by default | Excluded unless `include_hidden=True` |
| Domain alias is requested | Resolves to migrated target id |
| Runtime identity omits branch / turn / profile snapshot | Validation fails instead of fabricating branch readiness |
| Memory change event is created | Carries full identity, domain, layer, operation, source refs, dirty targets, and visibility effect |
| Registry is extended in a test | Generic list / lookup APIs return the added domain without service code changes |
| Bootstrap domain declares Recall / Archival as allowed layers | Registry returns matching read-only retrieval-backed templates with non-proposal permissions |
| Bootstrap `allowed_layers` and active templates diverge | Focused registry tests fail before runtime workers depend on incomplete templates |

### 5. Good / Base / Bad Cases

- Good: a runtime worker asks the registry which domains are active for `roleplay` and receives domain contracts without hardcoded `if mode == "roleplay"` service branches.
- Good: `knowledge_boundary` has separate block templates and permissions even if the first execution owner later maps to `CharacterMemoryWorker`.
- Good: every bootstrap domain declares Recall and Archival as allowed layers and also has matching read-only retrieval-backed templates, so later retrieval-card and evidence slices can resolve them without inventing local layer maps.
- Good: a projection refresh event records changed domain, source refs, and dirty packet/window consumers without becoming the source of current projection truth.
- Base: existing longform memory reads keep working through current Core State / Block services while the registry skeleton is introduced beside them.
- Bad: adding another local list of valid domains inside a worker or read service.
- Bad: declaring `recall` or `archival` as allowed layers while only providing Core State / Runtime Workspace templates.
- Bad: treating `StorySession.current_state_json` as the owner of new domain semantics.
- Bad: letting memory events become a hidden alternate truth store.

### 6. Tests Required

- Registry model/service tests cover:
  - all 13 bootstrap domains;
  - lifecycle filtering;
  - alias / migration resolution;
  - mode activation defaults;
  - declared allowed layers matching active block templates;
  - Recall / Archival templates staying read-only and non-proposal by default;
  - added test-only domain without unrelated service edits.
- DSL compatibility tests cover `knowledge_boundary` and `rule_state` as current bootstrap values where typed current DTOs need them.
- Identity tests cover required `story_id`, `session_id`, `branch_head_id`, `turn_id`, and `runtime_profile_snapshot_id`.
- Event tests cover source refs, dirty targets, visibility effect, and full identity propagation.
- Focused lint/type checks must include the new models, registry service, and tests.

### 7. Wrong vs Correct

#### Wrong

```python
if mode == "longform":
    domains = ["chapter", "narrative_progress", "foreshadow"]
```

This repeats domain policy inside a caller and forces every later mode to edit unrelated code.

#### Correct

```python
domains = registry_service.list_domains(mode=mode)
```

The declarative registry owns the domain vocabulary and activation defaults.

#### Wrong

```python
event = {"session_id": session_id, "domain": domain, "payload": payload}
```

This cannot support branch visibility, rollback, worker dirty checks, or pinned runtime policy.

#### Correct

```python
event = MemoryChangeEvent(identity=identity, domain=domain, ...)
```

The event carries the full story / branch / turn / profile identity while the underlying store remains the source of truth.
