# Current Memory Context

## Purpose

This file gives Phase 2 implementation/check agents a compact, current-memory-layer orientation. It exists because the repository's real Trellis spec currently has shared thinking guides and frontend placeholders, but no backend/RP-memory spec.

## Source Documents Read

- `docs/research/rp-redesign/core-state-memory-detailed-design.md`
- `docs/research/rp-redesign/new-architecture-overview.md`
- `docs/research/rp-redesign/x08-memory-os-redesign-draft.md`
- `docs/research/rp-redesign/agent/cooperation/claude-memory-os-block-container-proposal.md`
- `docs/research/rp-redesign/agent/cooperation/codex-memory-os-block-proposal-review-and-alignment.md`
- `docs/research/rp-redesign/memory-research/01-letta-memory-research.md`

## Stable Architecture Mouthfuls

- `Core State` is the current-story state center.
- `Core State.authoritative_state` is runtime truth.
- `Core State.derived_projection` is the durable current view for writer/orchestrator/UI/debug/export.
- `Recall Memory` stores past history: chapter/section summaries, transcripts, closed-scene material, and prose chunks.
- `Archival Knowledge` stores long-term source material: world book, character files, rule text, imported documents, and external reference material.
- `Runtime Workspace` stores current-turn temporary material: retrieval hits, tool outputs, in-flight candidate patches, and packet-building scratch state.

## Compatibility Mirror Meaning

`StorySession.current_state_json` currently stores the compatibility mirror for authoritative Core State fields. The mapped MVP fields are:

- `chapter_digest` -> `chapter.current`
- `narrative_progress` -> `narrative_progress.current`
- `timeline_spine` -> `timeline.event_spine`
- `active_threads` -> `plot_thread.active`
- `foreshadow_registry` -> `foreshadow.registry`
- `character_state_digest` -> `character.state_digest`

These fields are treated as compressed authoritative state in the current MVP, even when the field name contains `digest`.

`ChapterWorkspace.builder_snapshot_json` currently stores the compatibility mirror for settled projection slots. The mapped MVP slots are:

- `foundation_digest` -> `projection.foundation_digest`
- `blueprint_digest` -> `projection.blueprint_digest`
- `current_outline_digest` -> `projection.current_outline_digest`
- `recent_segment_digest` -> `projection.recent_segment_digest`
- `current_state_digest` -> `projection.current_state_digest`

These are writer-facing/current-view projections, not authoritative truth.

## Current Code Anchors

- `backend/rp/models/dsl.py`: frozen `Layer`, `Domain`, and `ObjectRef` identity vocabulary.
- `backend/models/rp_core_state_store.py`: formal Core State SQLModel tables.
- `backend/rp/services/core_state_store_repository.py`: current/revision repository for authoritative objects and projection slots.
- `backend/rp/services/memory_object_mapper.py`: authoritative and projection binding maps between legacy mirror fields and formal Core State refs.
- `backend/rp/services/core_state_dual_write_service.py`: activation seeding, dual-write, write-switch, projection sync, and materialization.
- `backend/rp/services/core_state_backfill_service.py`: backfill from compatibility mirrors into formal store.
- `backend/rp/services/core_state_read_service.py`: authoritative read service over formal store with mirror fallback.
- `backend/rp/services/projection_read_service.py`: settled projection read service over formal store with mirror fallback.
- `backend/rp/services/version_history_read_service.py`: version reads for authoritative/projection targets.
- `backend/rp/services/provenance_read_service.py`: provenance reads for authoritative/projection targets.
- `backend/rp/services/memory_inspection_read_service.py`: read-only memory inspection surface.
- `backend/rp/services/retrieval_broker.py`: unified memory query surface for state, summary, recall, archival, versions, and provenance.
- `backend/rp/tools/memory_crud_provider.py`: local MCP tool surface for memory CRUD/query/proposal tools.
- `backend/rp/services/writing_packet_builder.py`: deterministic writer packet builder that must remain a business boundary.
- `backend/rp/services/setup_agent_runtime_state_service.py` and `backend/rp/agent_runtime/contracts.py`: setup runtime-private cognition boundary.

## Current Implementation Status

Already real:

- Formal Core State tables for current rows and revision chains.
- Store repository with upsert/list/get operations.
- Dual-write and backfill paths.
- Read-side services that can use formal store or compatibility mirror fallback.
- Version/provenance services.
- Memory inspection API metadata that labels backend/source.
- Proposal/apply path connected to Core State write switch.
- Regression tests around schema, dual-write, backfill, read switch, lineage, provider tools, and controller memory read side.

Still missing:

- First-class `RpBlock` or equivalent Block envelope model.
- A Block read service over Core State rows/mirrors.
- Attach/mount relationships between blocks and active consumers.
- Dirty/fan-out mechanism for active consumers.
- Internal compile layer for non-writer agent contexts.
- Governed Block edit API.
- Memory visibility surface expressed in Block/container terms.

## Block Proposal Alignment

Keep from the original Block proposal:

- Block/container identity is valuable.
- A stable memory container shape is needed before compile/fan-out/edit can be implemented cleanly.
- Letta's separation between core blocks and recall/archival passages is relevant.
- Prompt-affecting changes should eventually become explicit dirty/rebuild events.

Narrow per review/alignment:

- `RpBlock` should initially land on Core State authoritative/projection objects, not replace the retrieval-core physical model for Recall/Archival.
- `Memory.compile()` can later unify internal agent context compilation, but it must not replace `WritingPacketBuilder`.
- Setup runtime-private cognition stays outside story durable Memory OS.
- Fan-out should be triggered by active durable memory revision changes and attached consumer dirty flags, not by `SetupWorkspace` changes directly.
- `domain` is a coarse classification, not the complete block identity. Exact identity needs `layer`, `domain`, `domain_path` or `object_id`, `scope`, and `revision`.

## Recommended First Implementation Stage

Implement a read-only Block envelope/read-model slice over existing Core State:

1. Add a focused `RpBlockView` or equivalent Pydantic model in the RP model layer.
2. Add a service that can list/read Block envelopes for authoritative Core State objects and projection slots.
3. Preserve formal-store route metadata when rows exist.
4. Preserve compatibility mirror route metadata when falling back.
5. Add tests that prove identity, layer/domain/path/scope, revision, and payload are preserved.

Do not add a new durable `rp_blocks` table in this stage. The existing formal Core State store is the source for Core State; the Block envelope is an adapter/read model.

## Validation Targets To Prefer

- Existing focused Core State tests:
  - `backend/rp/tests/test_core_state_store_schema.py`
  - `backend/rp/tests/test_core_state_backfill_service.py`
  - `backend/rp/tests/test_core_state_dual_write_services.py`
  - `backend/rp/tests/test_core_state_store_read_switch.py`
  - `backend/rp/tests/test_memory_lineage_services.py`
  - `backend/rp/tests/test_memory_crud_provider.py`
  - `backend/rp/tests/test_story_runtime_controller_memory_read_side.py`
- Add a new focused test file for the Block envelope service/model.

## Risks

- Adding Block as a new storage layer too early would duplicate Core State and retrieval-core storage.
- Treating `domain` as label/object identity would make exact reads and versions ambiguous.
- Letting compiler work touch `WritingPacketBuilder` would collapse the writer boundary.
- Putting setup cognition into durable Memory OS would mix agent-private reasoning with story truth.
- Removing compatibility mirror fallback too early would break migration and rollback paths.
