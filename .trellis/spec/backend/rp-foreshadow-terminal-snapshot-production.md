# RP Foreshadow Terminal Snapshot Production

## Scenario: Chapter-close fallback emits authoritative terminal foreshadow snapshots from explicit accepted-segment metadata

### 1. Scope / Trigger

- Trigger: `retired_foreshadow_summary` Recall retention already consumes authoritative terminal snapshots, but the current repo still lacks a real producer in the normal chapter-close path.
- Applies to RP backend implementation across:
  - `LongformSpecialistService._fallback_bundle(...)` for `LongformTurnCommandKind.COMPLETE_CHAPTER`;
  - accepted `StoryArtifact.metadata`;
  - append-only `state_patch_proposals["foreshadow_registry"]`;
  - the existing proposal/apply workflow used by heavy regression;
  - focused foreshadow production / retired-foreshadow regression tests.
- This slice does **not** add a new public tool, new storage layer, or generic `set_status` execution path.
- This slice does **not** infer foreshadow retirement from prose, `summary_updates[]`, Runtime Workspace discussion, or retrieval hits.

### 2. Signatures / Surfaces

Accepted-segment metadata input:

```python
StoryArtifact.metadata["foreshadow_status_updates"] = [
    {
        "foreshadow_id": "envoy_debt",
        "status": "resolved",
        "summary": "bell tower debt",
        "resolution": "Settled at the river gate.",
    }
]
```

Fallback output surface:

```python
SpecialistResultBundle.state_patch_proposals["foreshadow_registry"] = [
    {
        "foreshadow_id": "envoy_debt",
        "status": "resolved",
        "summary": "bell tower debt",
        "resolution": "Settled at the river gate.",
    }
]
```

Existing apply path that must remain unchanged:

```python
LongformRegressionService._apply_bundle(...)
-> LegacyStatePatchProposalBuilder.build_inputs(...)
-> ProposalWorkflowService.submit_and_route(...)
-> StoryStateApplyService.apply(...)
```

### 3. Contracts

- Producer root:
  - current repo truth is that `COMPLETE_CHAPTER` returns `LongformSpecialistService._fallback_bundle(...)` directly instead of a specialist LLM JSON result;
  - therefore chapter-close foreshadow terminal snapshot production must happen inside the fallback path until a later slice replaces that producer.
- Input contract:
  - only accepted `StoryArtifact` items passed into heavy regression are scanned;
  - only `metadata["foreshadow_status_updates"]` is read in this slice;
  - the value must be a list, and only `dict` items are eligible.
- Terminal eligibility:
  - require non-blank `foreshadow_id`;
  - require explicit terminal marker at `status` or `state`;
  - recognized terminal values in this slice are `resolved`, `retired`, and `closed`;
  - non-terminal or markerless updates are skipped.
- Normalization rules:
  - emitted snapshots stay append-only `dict` payloads under `foreshadow_registry`;
  - the emitted snapshot must carry canonical `status=<terminal_value>` even when the input only used `state`;
  - additional explicit fields such as `summary`, `title`, `description`, `resolution`, or other structured payload fields may pass through unchanged.
- Selection rules:
  - later accepted segment wins over earlier accepted segment for the same `foreshadow_id`;
  - within the same segment metadata list, later item wins over earlier item for the same `foreshadow_id`;
  - emit at most one new terminal snapshot per `foreshadow_id` for one chapter-close bundle.
- Governance / write path:
  - chapter-close terminal snapshots must be emitted through `state_patch_proposals["foreshadow_registry"]`;
  - heavy regression must continue routing them through the existing append-only proposal/apply workflow;
  - this slice must not write `StorySession.current_state_json` directly.
- Idempotence:
  - if authoritative `foreshadow_registry` already contains the same normalized terminal snapshot, chapter-close rerun must not append it again;
  - dedupe is for exact normalized snapshot replay, not for semantic merging of different terminal snapshots.
- Boundary rules:
  - `summary_updates[]` remain summary/projection/continuity material, not authoritative foreshadow producer input;
  - light regression does not consume this metadata in this slice;
  - Recall ingestion remains a downstream consumer of authoritative terminal snapshots, not the producer itself.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| No accepted segments or no `foreshadow_status_updates` metadata | Emit no `foreshadow_registry` patch |
| Metadata value is not a list | Emit no `foreshadow_registry` patch |
| Metadata item is not a dict | Skip that item |
| `foreshadow_id` is blank after normalization | Skip that item |
| Update has `state="closed"` and no `status` | Emit a snapshot with canonical `status="closed"` |
| Update has `status="active"` | Skip that item in this slice |
| Same `foreshadow_id` has multiple terminal updates in one chapter close | Emit only the last normalized terminal snapshot |
| Same normalized terminal snapshot already exists in authoritative `foreshadow_registry` | Emit nothing for that snapshot on rerun |
| Heavy regression reruns with unchanged accepted-segment metadata | Do not duplicate authoritative append entries |
| Recall ingestion later runs after apply | Consume the updated authoritative `foreshadow_registry` without any new direct producer path |

### 5. Good / Base / Bad Cases

- Good: an accepted segment explicitly carries `foreshadow_status_updates=[{"foreshadow_id": "envoy_debt", "status": "resolved"}]`; chapter close emits one append-only authoritative foreshadow snapshot, and downstream retired-foreshadow Recall ingestion can consume it.
- Good: a later accepted segment carries a newer terminal update for the same `foreshadow_id`; only the later snapshot is emitted for that chapter close.
- Base: accepted segments have no foreshadow metadata; chapter close leaves `foreshadow_registry` unchanged.
- Bad: scanning accepted prose text and guessing that a foreshadow must be resolved.
- Bad: using `summary_updates[]` as authoritative foreshadow producer input.
- Bad: adding a new generic mutation surface just to flip foreshadow status in place.

### 6. Tests Required

- Fallback/producer tests:
  - real heavy-regression `COMPLETE_CHAPTER` path emits terminal `foreshadow_registry` snapshots from accepted-segment metadata;
  - non-terminal, blank-id, and malformed metadata items are skipped;
  - later terminal snapshot wins per `foreshadow_id`.
- Governance/idempotence tests:
  - emitted snapshots route through the existing proposal/apply append path;
  - chapter-close rerun with unchanged metadata does not duplicate the authoritative registry.
- Downstream retention tests:
  - retired-foreshadow Recall ingestion can materialize from the real runtime output of heavy regression rather than a monkeypatched post-apply session.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: infer foreshadow retirement from prose or summary updates.
if "debt settled" in accepted_segment.content_text:
    state_patch["foreshadow_registry"] = [{"foreshadow_id": "envoy_debt", "status": "resolved"}]
```

#### Correct

```python
# Correct: only explicit structured metadata can become authoritative
# chapter-close foreshadow terminal snapshots in this slice.
for update in accepted_segment.metadata.get("foreshadow_status_updates", []):
    if update.get("status") in {"resolved", "retired", "closed"}:
        state_patch["foreshadow_registry"].append(update)
```

## Status on 2026-04-28

- `COMPLETE_CHAPTER` fallback now owns the current authoritative terminal-foreshadow producer path.
- Accepted `story_segment` metadata can carry explicit `foreshadow_status_updates`, and heavy regression turns those into append-only `foreshadow_registry` proposals.
- The producer remains conservative:
  - only explicit terminal `status` / `state` values are accepted;
  - only one latest terminal snapshot per `foreshadow_id` is emitted per chapter close;
  - identical reruns do not duplicate authoritative snapshots.
- Public memory tools and durable storage boundaries remain unchanged.
