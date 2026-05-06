# Story Segment Structured Metadata Gap

## Why this note exists

The current memory-layer gap is no longer downstream Recall consumption. The real missing contract is upstream: who produces stable structured metadata that accepted `story_segment` artifacts can carry into later chapter-close maintenance.

## Current confirmed facts

- `LongformSpecialistService._build_terminal_foreshadow_patch(...)` already consumes accepted `StoryArtifact.metadata["foreshadow_status_updates"]` during `COMPLETE_CHAPTER`.
- `RecallRetiredForeshadowIngestionService` already consumes authoritative `foreshadow_registry` after apply.
- `StoryTurnDomainService._persist_generated_artifact_impl(...)` currently persists only:
  - `command_kind`
  - `packet_id`
  - `writer_hints`
- `WritingWorkerExecutionService.run(...)` still returns text only.
- `LongformOrchestratorService.plan(...)` and `LongformSpecialistService.analyze(...)` both fallback directly for `ACCEPT_OUTLINE`, `ACCEPT_PENDING_SEGMENT`, and `COMPLETE_CHAPTER`.

## Practical conclusion

This remains a memory-mainline task, but the next implementation surface is upstream runtime/specialist/artifact metadata rather than Recall itself.

The smallest honest slice is:

1. freeze a typed specialist-owned sidecar contract;
2. normalize and persist it on draft `story_segment` artifacts;
3. let existing accept / complete-chapter consumers read it without any prose inference.

## Boundaries to preserve

- Do not replace `WritingPacketBuilder`.
- Do not widen `summary_updates[]` into authoritative truth.
- Do not parse writer prose into metadata.
- Do not add a new truth write path outside proposal/apply.
- Do not invent a generic free-form artifact metadata family in this slice.
