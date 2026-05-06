# Registry Profile Snapshot Full Management Technical Research

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Goal: capture the minimal research that materially shapes the full-management registry/profile spec after the boot compiler.

## 1. Current Repo Evidence

Current code/spec anchors:

- `backend/rp/services/memory_contract_registry.py`
- `backend/rp/models/memory_contract_registry.py`
- `backend/rp/services/retrieval_runtime_config_service.py`
- `backend/rp/services/story_session_service.py`
- `.trellis/spec/backend/rp-runtime-profile-snapshot-minimal-compiler.md`
- `.trellis/spec/backend/rp-memory-contract-registry-identity-event-skeleton.md`

What the repo already proves:

1. bootstrap domain/block vocabulary is already declarative and mode-aware enough to seed a real registry.
2. retrieval config resolution already has a real overlay pattern: setup workspace base + story session override.
3. the missing piece is persistence/management of descriptors and profiles, not the concept of compilation itself.

What is still weak:

1. registry is still static/read-only bootstrap data;
2. worker/domain/block changes still require code edits;
3. snapshot compilation is not yet backed by persistent mode/profile definitions.

## 2. Reuse Decision

Keep and extend:

- current `MemoryDomainContract` / `MemoryBlockTemplate` / mode-default model family;
- bootstrap registry as seed defaults;
- the boot `RuntimeProfileSnapshot` compiler contract;
- existing story/runtime config overlay pattern.

Do not add:

- UI-first marketplace mechanics;
- hardcoded longform/roleplay/TRPG branches in runtime services;
- a second profile compiler separate from the boot compiler.

Why:

- the current model vocabulary is already good enough to become the persistent source format;
- the missing work is persistence, publish/activate flow, and migration/alias governance.

## 3. Mature Wheel / Framework Decision

No external plugin or dynamic config framework should be introduced now.

Reason:

- the project-specific registry semantics are already modeled locally;
- the user explicitly wants backend structure not hardcoded, but does not require marketplace complexity in phase one;
- SQLModel persistence plus controlled compiler services are enough.

## 4. Spec Consequences

The full-management registry/profile spec should:

1. keep bootstrap registry as defaults/seed only;
2. add persistent descriptor/profile records that can override or extend bootstrap entries;
3. support add/disable/hide/migrate without editing story runtime core services;
4. compile published mode profiles into immutable `RuntimeProfileSnapshot` records;
5. keep usable defaults so runtime does not require manual zero-to-one configuration.

## 5. Rejected Alternatives

Rejected: keep registry purely in Python constants and solve customization through session JSON patches.

- That makes migrations, disablement, and descriptor provenance opaque.
- It keeps runtime services too dependent on current mutable config blobs.

Rejected: design full operator UI/API complexity before persistent compiler inputs exist.

- The immediate need is backend-managed descriptors and snapshots.
- UI polish can layer on later once the backend contracts are stable.
