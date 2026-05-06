# RP Registry Profile Snapshot Full Management

## Scenario: bootstrap registry and minimal snapshot compiler grow into persistent, configurable domain/block/worker/profile management without hardcoding longform behavior into runtime services

### 1. Scope / Trigger

- Trigger: boot-bar planning introduces a real `RuntimeProfileSnapshot` compiler and pinning semantics, but full runtime foundation still needs persistent registry/profile management so new domains, blocks, workers, and permission policies do not require editing story runtime core services.
- Applies to backend RP memory/runtime contract work for:
  - persistent registry descriptor management;
  - persistent mode/profile definitions;
  - publish/activate compilation into immutable `RuntimeProfileSnapshot` records;
  - alias/migration/deprecation governance;
  - focused registry/profile compilation tests.
- This slice must not:
  - require a full operator UI before the backend is usable;
  - introduce marketplace-style plugin complexity;
  - fork a second snapshot compiler separate from the boot compiler;
  - hardcode longform-specific runtime logic back into the scheduler/mutation kernel.

### 2. Surfaces

Representative persistent records:

```python
class MemoryDomainDescriptorRecord(SQLModel, table=True):
    domain_id: str
    version: int
    lifecycle: str
    config_json: dict[str, Any]


class MemoryWorkerDescriptorRecord(SQLModel, table=True):
    worker_id: str
    version: int
    lifecycle: str
    config_json: dict[str, Any]


class MemoryBlockTemplateDescriptorRecord(SQLModel, table=True):
    block_template_id: str
    domain_id: str
    version: int
    lifecycle: str
    config_json: dict[str, Any]


class MemoryModeProfileRecord(SQLModel, table=True):
    profile_id: str
    mode: str
    version: int
    status: str
    config_json: dict[str, Any]
```

Management/compiler service:

```python
class MemoryRegistryManagementService:
    def publish_mode_profile(self, *, profile_id: str, actor: str) -> str: ...
    def activate_mode_profile(self, *, profile_id: str, actor: str) -> str: ...
    def list_worker_descriptors(self, *, mode: str | None = None) -> list[dict[str, Any]]: ...
    def list_domain_descriptors(self, *, include_hidden: bool = False) -> list[dict[str, Any]]: ...
    def list_block_template_descriptors(self, *, domain_id: str | None = None) -> list[dict[str, Any]]: ...
```

### 3. Contracts

#### Bootstrap-seed contract

- The bootstrap registry remains valid and useful.
- It becomes the seed/default layer, not the only source of truth.
- Persistent/config-backed descriptors may override or extend bootstrap descriptors in a controlled way.

#### Descriptor contract

- Domain, block, and worker descriptors must be persistable, versioned, and lifecycle-aware.
- Lifecycle states must support at least:
  - `active`
  - `hidden`
  - `retired`
  - `migrated`
- Alias/migration rules must be deterministic so older refs can still resolve after rename or replacement.
- Block template ids and aliases must also be globally unique within the effective registry so resolver maps cannot silently overwrite one descriptor with another.
- Management lifecycle operations must cover block templates as well as domains and workers:
  - hide
  - retire
  - migrate
- Worker-to-domain/block bindings must come from descriptor/config data and compiled profiles, not hardcoded runtime branches.

#### Mode/profile contract

- Mode profiles must compile from registry/config inputs into immutable `RuntimeProfileSnapshot` records.
- A published/activated profile is the source of future turn snapshots until superseded.
- Turn-start still pins one immutable snapshot; profile changes affect future turns only.

#### Runtime extensibility contract

- Adding or disabling a roleplay/TRPG domain or worker must not require editing:
  - story runtime core scheduler logic;
  - memory mutation kernel;
  - branch visibility resolver;
  - read manifest contract.
- Core services should consume compiled descriptors/profiles, not hardcoded mode branches.

#### Policy compilation contract

- Full management must compile more than domain activation:
  - worker activation
  - permission levels
  - retrieval policy
  - context/packet policy
  - mode-specific worker/model/vendor config
- The compiler must reuse the boot snapshot contract instead of inventing a new snapshot model family.

#### Default-usable contract

- Runtime must still ship with working defaults.
- The backend must not require every project/user to author descriptors from zero before runtime can run.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| No custom registry/profile config exists | Bootstrap defaults still compile into usable active snapshots |
| A new worker/domain/block descriptor is added through config/persistence | Core services resolve it without code edits in the scheduler/mutation kernel |
| A domain or worker is disabled | Future compiled snapshots exclude or deny it deterministically |
| A domain/worker is migrated/aliased | Older refs resolve through migration rules |
| A profile is published/activated | Future turns can pin snapshots compiled from that effective config |
| Session config changes after a turn starts | Existing pinned snapshot for that turn does not drift |

### 5. Good / Base / Bad Cases

- Good: roleplay introduces a new worker descriptor and a new block template descriptor by registry/profile configuration, and the scheduler sees them through the compiled snapshot without a new `if mode == "roleplay"` branch.
- Good: TRPG disables one worker in a future profile version, and future turns reject it while earlier turns keep their pinned snapshots.
- Good: bootstrap defaults remain usable for stories that never customize descriptors.
- Base: phase one can stay backend-only; UI can layer on later.
- Bad: using session JSON blobs as the only effective registry/profile source.
- Bad: adding new mode behavior by editing unrelated core scheduler/mutation services.
- Bad: building a second snapshot compiler path for “advanced” configuration.

### 6. Tests Required

- Descriptor tests cover:
  - add/hide/retire/migrate behavior;
  - alias resolution;
  - active domain/block/worker descriptor listing by mode.
- Compiler tests cover:
  - bootstrap-only compile;
  - config-backed overrides/extensions;
  - publish/activate -> immutable snapshot behavior;
  - future-turn-only effect of profile changes.
- Boundary tests cover:
  - new descriptors do not require code changes in core scheduler/memory kernel paths;
  - defaults remain usable when no custom config exists.
- Focused lint/type checks must include the registry/profile full-management contract and tests.

### 7. Wrong vs Correct

#### Wrong

```python
if mode == "trpg":
    workers = ["rules_worker", "inventory_worker"]
```

This hardcodes mode policy back into runtime services instead of letting compiled descriptors drive behavior.

#### Correct

```python
snapshot_id = registry_management_service.activate_mode_profile(
    profile_id="trpg_default_v2",
    actor="system",
)
```

The backend compiles and activates a profile that future turns pin immutably, while runtime services read behavior from the snapshot rather than from scattered mode branches.
