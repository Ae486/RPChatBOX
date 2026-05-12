# RP Core Projection And Read Manifest Hardening

## Scenario: strict fact/view separation and deterministic packet-visible read contracts before writer retrieval and post-write maintenance depend on ad hoc context assembly

### 1. Scope / Trigger

- Trigger: base-revision enforcement, projection refresh freshness metadata, boot-bar identity, and branch visibility work are now strong enough that runtime can stop leaning on compatibility mirrors and ad hoc packet assembly. The next contract must freeze Core fact vs Projection/View boundaries and define a deterministic read manifest for packet-visible context.
- Applies to backend RP memory/runtime contract work for:
  - runtime-owned projection refresh hardening;
  - strict current fact vs derived view rules;
  - deterministic read manifest fields for writer/scheduler packet assembly;
  - packet-visible source ref / revision / omission metadata;
  - focused read-manifest and projection-path tests.
- This slice must not:
  - replace `WritingPacketBuilder`;
  - create a new orchestration framework;
  - expose chain-of-thought or hidden planning text;
  - allow retrieval hits to bypass governed promotion into Core truth.

### 2. Surfaces

Read manifest contract:

```python
class RuntimeReadManifest(BaseModel):
    manifest_id: str
    identity: MemoryRuntimeIdentity
    active_branch_lineage: list[str]
    branch_scope: dict[str, Any] = Field(default_factory=dict)
    core_state_snapshot_id: str | None = None
    core_state_revision_map: dict[str, str] = Field(default_factory=dict)
    projection_source_manifest_id: str | None = None
    runtime_profile_snapshot_id: str
    policy_versions: dict[str, str]
    visible_refs: list[dict[str, Any]]
    selected_refs: list[dict[str, Any]]
    omitted_refs: list[dict[str, Any]]
    packet_sections: list[dict[str, Any]]
    retrieval_card_refs: list[str]
    expanded_chunk_refs: list[str]
    retrieval_miss_refs: list[str]
    writer_usage_refs: list[str]
    token_usage_metadata: dict[str, Any]
```

Service surface:

```python
class RuntimeReadManifestService:
    def build_writer_manifest(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        packet_kind: str,
    ) -> RuntimeReadManifest: ...
```

Projection refresh runtime-path rule:

```python
class ProjectionRefreshRequest(BaseModel):
    identity: MemoryRuntimeIdentity | None = None
    ...
```

Stable error codes:

```text
runtime_read_manifest_identity_required
runtime_read_manifest_branch_scope_missing
projection_refresh_identity_required
```

### 3. Contracts

#### Fact vs view contract

- `Core State.authoritative_state` is the only current truth layer.
- `Core State.derived_projection` is a derived current view.
- Runtime-owned Core truth is selected by Core State as-of manifest and object
  revision map. Latest current object rows are caches/compatibility views, not
  selected-turn truth.
- Runtime-owned projection refresh is maintenance over view state only.
- Runtime-owned reads and packet assembly must not treat:
  - compatibility mirrors
  - Runtime Workspace material
  - Recall hits
  - Archival hits
as authoritative fact by default.

#### Runtime-owned projection refresh contract

- Legacy compatibility path may still allow `ProjectionRefreshRequest.identity=None`.
- Runtime-owned projection refresh paths must require full `MemoryRuntimeIdentity`.
- Runtime-owned refresh must already be compatible with:
  - base revision checks
  - authoritative source revision checks
  - dirty target recording
  - later persistent event recording
- Identity-free bundle refresh is compatibility-only, not the boot-bar runtime baseline.

#### Read manifest contract

- Every writer/scheduler packet build must be able to persist or reconstruct a deterministic read manifest.
- The manifest must answer:
  - what was visible to this runtime turn;
  - which Core State snapshot manifest and object revisions defined the
    selected-turn authoritative state;
  - what was selected into the packet;
  - what was omitted and why;
  - which revisions/hashes/refs backed the packet;
  - which retrieval cards/expansions/usages participated.
- The manifest is a read/trace contract, not a new LLM orchestration layer.
- `WritingPacketBuilder` remains the packet builder; the manifest is the deterministic input/trace contract around it.
- If a projection section is derived from a different Core manifest/revision set
  than the selected runtime turn, the manifest must mark it stale/omitted or
  trigger refresh. It must not silently substitute latest-session projection.

#### Core as-of read contract

- Runtime-owned Core reads must resolve:
  - `branch_scope`;
  - `core_state_snapshot_id`;
  - `core_state_revision_map`.
- A manifest's `core_state_revision_map` maps stable object ref ids to exact
  object revision ids or `object_id@revision` refs.
- Writer context and Memory inspection must use the same Core as-of manifest for
  the selected branch/turn.
- Compatibility fallback to `StorySession.current_state_json` or latest current
  row is allowed only on explicit legacy/admin paths and must be visible in
  warnings/metadata. It must not feed runtime writer context.
- Projection slots must record their source Core manifest id or source revision
  map so freshness can be checked deterministically.

#### Visible vs selected contract

- `visible_refs` = candidates available under identity + branch visibility + policy.
- `selected_refs` = packet-visible refs actually included.
- `omitted_refs` = refs considered but excluded, with deterministic reason metadata such as:
  - budget trim
  - policy disallow
  - superseded
  - branch hidden
  - duplicate/covered by stronger ref
- The manifest must not expose hidden model reasoning; it only exposes deterministic backend selection metadata.

#### Packet section classification contract

- Packet/debug/read surfaces must classify packet sections through stable backend-authored fields, not presentation labels or payload-private hints.
- A packet section that represents mode/runtime sidecar material must expose at least one stable classifier:
  - `metadata.section_family == "mode_sidecar"`;
  - or `source_kind in {"mode_sidecar", "runtime_mode_sidecar"}`;
  - or a stable `section_id` namespace such as `mode_sidecar.<slot_id>`.
- Labels are display text only. Debug/read code must not decide whether a section is a mode sidecar from `label`, localized text, or prose payload content.
- When a section is selected into `packet_sections`, its `source_ref_ids` must point at formal refs or typed Runtime Workspace material refs rather than payload-local provenance.

#### Retrieval contract

- Retrieval cards remain Runtime Workspace material until later governed promotion.
- The read manifest may record:
  - retrieval card refs
  - expanded chunk refs
  - retrieval miss refs
  - writer usage refs
- Retrieval participation in a packet does not change Core truth by itself.

#### Compatibility contract

- Compatibility mirrors may remain as fallback routes during transition.
- Boot-bar runtime packet assembly must still produce manifest-grade source/ref metadata even while some reads come from compatibility routes.
- This slice does not require full persistence of manifests if reconstructable fields are already durable and exact.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Runtime-owned packet build starts without full identity | Reject with `runtime_read_manifest_identity_required` |
| Runtime-owned packet build lacks branch scope | Reject with `runtime_read_manifest_branch_scope_missing` |
| Runtime-owned projection refresh is attempted without identity | Reject with `projection_refresh_identity_required` |
| Same identity + same store state + same profile snapshot | Same read manifest content is produced |
| Core manifest is selected for turn N | Manifest records `core_state_snapshot_id` and exact object revision refs |
| Projection source manifest differs from selected Core manifest | Projection is refreshed or omitted with `core_projection_source_manifest_mismatch` |
| Ref is visible but trimmed by budget | Appears in `omitted_refs` with deterministic reason |
| Retrieval card enters packet | Appears in manifest retrieval refs, but not as Core truth |
| Compatibility mirror read is used | Manifest still records route/source version metadata |
| Mode sidecar enters packet | Section carries stable `section_family` / `source_kind` / `section_id` classifier and formal source refs |
| Debug reader sees a sidecar-looking label without stable classifier | Treat as ordinary packet section, not as mode sidecar |

### 5. Good / Base / Bad Cases

- Good: a writer packet shows which Core refs, Projection slots, Runtime Workspace refs, and retrieval cards were selected for that exact turn.
- Good: a writer packet built after branching from turn 2 records the turn 2
  Core manifest and excludes later Core current-row values.
- Good: the same turn can be debugged later without exposing hidden chain-of-thought, only deterministic selection metadata.
- Good: projection refresh remains derived-view maintenance with identity and freshness guards.
- Good: `mode_sidecar.rule_card` is discoverable in debug/read views through `metadata.section_family` and `source_ref_ids`, even if its display label changes.
- Base: legacy compatibility routes can remain during transition if the manifest records their route/source metadata.
- Bad: assembling packet context through ad hoc service calls with no reproducible visible/selected/omitted ref contract.
- Bad: recording only latest current Core row metadata in a runtime manifest when
  the selected turn should read an older manifest.
- Bad: letting runtime-owned projection refresh keep omitting identity indefinitely.
- Bad: treating retrieval hits selected into the packet as if they were already Core truth.
- Bad: treating a section as a TRPG/rule sidecar because its label contains "rule" while the manifest lacks a stable section classifier.

### 6. Tests Required

- Manifest tests cover:
  - deterministic output for same identity/state/profile;
  - `core_state_snapshot_id` and `core_state_revision_map` for runtime-owned
    writer turns;
  - projection source manifest mismatch produces refresh or omitted reason;
  - visible vs selected vs omitted separation;
  - packet section source/revision/hash metadata;
  - packet section family classification through stable fields, not labels;
  - retrieval card/expansion/usage ref recording.
- Projection tests cover:
  - runtime-owned refresh rejects missing identity;
  - compatibility-only refresh path stays explicit and bounded.
- Integration tests cover:
  - packet builder can consume manifest-derived refs without leaking raw authoritative JSON or raw retrieval dumps.
- Focused lint/type checks must include the new manifest contract and projection-path changes/tests.

### 7. Wrong vs Correct

#### Wrong

```python
manifest = RuntimeReadManifest(
    identity=identity,
    active_branch_lineage=[identity.branch_head_id],
    visible_refs=[],
    selected_refs=[],
    omitted_refs=[],
)
```

This records branch identity but not the Core State snapshot/revision set that
made the packet's authoritative state reproducible.

#### Correct

```python
manifest = RuntimeReadManifest(
    identity=identity,
    active_branch_lineage=scope.visible_branch_head_ids,
    branch_scope=scope.model_dump(mode="json"),
    core_state_snapshot_id=core_manifest.snapshot_id,
    core_state_revision_map=core_manifest.effective_revision_map,
    projection_source_manifest_id=projection.source_manifest_id,
    visible_refs=visible_refs,
    selected_refs=selected_refs,
    omitted_refs=omitted_refs,
)
```

The packet can be reproduced against the selected branch/turn Core truth, and
stale projection sources can be detected deterministically.

#### Wrong

```python
packet_sections = projection_sections + raw_retrieval_hits + recent_logs
```

This gives no reproducible visible/selected/omitted contract and leaks the wrong materials into packet assembly.

#### Correct

```python
manifest = read_manifest_service.build_writer_manifest(
    identity=identity,
    packet_kind="writer",
)
```

The packet build stays deterministic, packet-visible inputs are explicit, and fact/view/retrieval boundaries remain intact.
