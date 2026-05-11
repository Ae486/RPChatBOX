# Story Runtime Product Wiring / Writer Constraint Closure Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Phase S / Product Wiring and Writer Constraint Closure
>
> Status: development-spec-v1
>
> Canonical requirement spec: [story-runtime-product-wiring-writer-constraint-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-product-wiring-writer-constraint-spec.md)

## 1. Scope / Trigger

This development spec is triggered by a product QA failure after Phase Q.

The work includes:

1. Backend rewrite packet constraint assembly.
2. Backend continuation packet constraint assembly.
3. Minimal frontend runtime inspect/config/read visibility.
4. Product-level tests that prove the real path works.

The work must not reclassify hidden backend service tests as product acceptance.

## 2. Module Split

### S1. Backend Writer Constraint Closure

Owner files:

- `backend/rp/services/story_turn_domain_service.py`
- `backend/rp/services/context_orchestration_service.py`
- `backend/rp/services/writing_packet_builder.py`
- `backend/rp/services/rewrite_request_builder_service.py`
- new helper service if useful, for example:
  `backend/rp/services/rewrite_packet_constraint_service.py`
- tests under `backend/rp/tests/`

Do not edit Flutter files in S1.

### S2. Frontend Runtime Visibility

Owner files:

- `lib/services/backend_story_service.dart`
- `lib/models/story_runtime.dart`
- `lib/pages/longform_story_page.dart`
- optionally a small widget file under `lib/widgets/` if the page becomes too large

Do not edit backend writer packet logic in S2.

### S3. Product Acceptance Re-run

Owner files:

- `backend/rp/tests/test_story_runtime_product_wiring_writer_constraints.py`
- `backend/rp/tests/test_story_runtime_product_acceptance.py` only if Q labels
  need clarification
- manual QA doc updates if needed

S3 runs after S1/S2 implementation and their module-level checks.

## 3. Backend Contract

### 3.1 Rewrite Constraint Service

Recommended service:

```python
class RewritePacketConstraintService:
    def build_review_overlay_sections(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        session: StorySession,
        chapter: ChapterWorkspace,
        target_artifact_id: str,
    ) -> list[dict[str, object]]: ...
```

Responsibilities:

1. Resolve the target pending draft artifact.
2. Find or require the draft document and active review overlay.
3. Read active comments and active tracked changes.
4. Build a `RewriteRequest` through `RewriteRequestBuilderService`.
5. Convert it to `review_overlay_sections`.
6. Return an empty list only when there are no active review constraints.
7. Raise a stable error when constraints exist but cannot be assembled.

### 3.2 Context Orchestration Input

`StoryTurnDomainService.build_packet(...)` must pass enough information for
packet construction:

```python
build_packet(
    *,
    session_id: str,
    plan: OrchestratorPlan,
    specialist_bundle: SpecialistResultBundle,
    command_kind: LongformTurnCommandKind | None = None,
    runtime_identity: MemoryRuntimeIdentity | None = None,
    target_artifact_id: str | None = None,
) -> WritingPacket
```

`ContextOrchestrationService.build_writing_packet(...)` must accept:

```python
command_kind: LongformTurnCommandKind | None
target_artifact_id: str | None
review_overlay_sections: list[dict[str, object]] | None
```

The exact signature can vary if the implementation chooses a small typed
context object, but the same information must reach packet assembly.

### 3.3 Rewrite Packet Rules

When `command_kind == rewrite_pending_segment`:

1. `operation_mode` must be `rewrite`.
2. `WritingPacket.review_overlay_sections` must include active comments/tracked
   changes when they exist.
3. `WritingPacket.metadata` must include:
   - `rewrite_scope`
   - `target_artifact_id`
   - `revision_constraint_source`
   - `review_overlay_section_count`
4. The rendered writer prompt must include the review overlay section.
5. The writer instruction must say that listed review constraints are mandatory.

### 3.4 Continuation Packet Rules

When `command_kind == write_next_segment` and accepted segments exist:

1. Packet must include a section such as `chapter_progress.continuity`.
2. The section must contain:
   - chapter index
   - chapter goal
   - accepted segment count
   - latest accepted segment excerpt
   - accepted outline digest or ref
   - direct next-step continuity instruction
3. The section must not be hidden only in `writer_hints`.
4. The instruction must include:
   - continue after the latest accepted segment
   - do not restart the scene
   - do not rewrite already completed outline material

The first implementation does not need a perfect outline beat cursor. It must
make the local continuity constraint explicit and testable. A structured beat
cursor can be a later slice.

## 4. Frontend Contract

### 4.1 Service Methods

Add to `BackendStoryService`:

```dart
Future<RpRuntimeInspection> getRuntimeInspection({
  required String sessionId,
  String? branchHeadId,
  String? turnId,
  int? targetChapterIndex,
});

Future<Map<String, dynamic>> getRuntimeDebug({required String sessionId});

Future<List<Map<String, dynamic>>> getRuntimeConfigHistory({
  required String sessionId,
});
```

DTO names can change, but the page must not pass raw `dynamic` everywhere.
Use typed wrappers with raw maps for complex subtrees.

### 4.2 Minimal Inspect Panel

Add a read-only entry in `LongformStoryPage`:

1. A top-level icon/button labelled in product language, for example `Runtime`.
2. A bottom sheet, side panel, or modal.
3. The panel displays:
   - current mode
   - active branch
   - selected turn
   - active runtime profile snapshot
   - runtime config status/history summary
   - writer packet summary
   - review overlay summary
   - chapter bridge summary
   - job ledger summary
   - retrieval summary
   - mode sidecar summary
   - branch control receipts if present
4. Empty/missing sections must show "not available" or equivalent product copy,
   not fail silently.

### 4.3 Candidate Semantics Copy

Candidate selector must make this explicit:

1. Selecting a candidate changes the preview.
2. It does not adopt that candidate.
3. Only Accept / Accept & Continue makes the selected candidate the continuation
   base.

The first implementation may remain local-preview based if backend selection
receipt wiring is not implemented in S2. If so, the UI must not imply persisted
selection.

## 5. Tests Required

### S1 Backend Tests

Required tests:

1. Real `rewrite_pending_segment` graph/domain path builds a writer packet with
   `review_overlay_sections` containing a comment and tracked change.
2. Writer prompt rendering includes the review overlay text and mandatory
   rewrite instruction.
3. Real `write_next_segment` packet includes chapter continuity/progress when
   accepted segments exist.
4. Rewrite fails closed when active review constraints exist but the target draft
   or draft document cannot be resolved.

Preferred file:

- `backend/rp/tests/test_story_runtime_product_wiring_writer_constraints.py`

### S2 Frontend Checks

Required checks:

1. Flutter analyzer/build check for touched files.
2. Unit-level model parsing test if existing frontend test pattern supports it.
3. Manual smoke path:
   - open longform page;
   - open Runtime/Inspect panel;
   - verify empty sections do not crash;
   - trigger write/rewrite;
   - verify panel can refresh and show selected ids.

### S3 Product QA

Manual QA must repeat the failed cases:

1. Add a revision comment that asks for a term replacement.
2. Rewrite and confirm inspect/prompt evidence contains the term replacement
   instruction.
3. Accept candidate and continue.
4. Confirm next output follows the latest accepted segment and does not jump
   backward to an earlier outline part.

## 6. Wrong vs Correct

### Wrong

`Rewrite` only sends:

```json
{
  "command_kind": "rewrite_pending_segment",
  "target_artifact_id": "artifact-123"
}
```

and the writer receives a generic instruction like "Rewrite the pending segment".

### Correct

`Rewrite` may still use the existing command, but backend packet assembly must
resolve the active review overlay and render a writer-visible section:

```json
{
  "label": "review_overlay",
  "source_kind": "review_overlay_rewrite_request",
  "items": [
    "Comment: replace term X with term Y",
    "Tracked change: original X -> suggested Y"
  ]
}
```

### Wrong

`Write Next Segment` only includes a vague outline digest and "Write the next
longform story segment".

### Correct

`Write Next Segment` includes an explicit continuity section:

```json
{
  "label": "chapter_progress",
  "items": [
    "accepted_segment_count: 3",
    "latest_accepted_segment_excerpt: ...",
    "next_required_continuity_instruction: Continue after the latest accepted segment; do not restart or rewrite completed outline material."
  ]
}
```

## 7. Parallel Implementation Rules

1. S1 and S2 may run in parallel.
2. S1 owns backend writer packet behavior and backend tests.
3. S2 owns Flutter visibility and copy.
4. Neither module may claim product acceptance complete until S3 reruns the
   manual QA path.
5. If S2 needs a backend field that S1 has not implemented, it must display the
   field as missing rather than invent a frontend-only meaning.

