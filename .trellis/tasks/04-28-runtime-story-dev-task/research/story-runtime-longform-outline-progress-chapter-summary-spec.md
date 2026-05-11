# Story Runtime Longform Outline Progress / Chapter Summary Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Phase T / Longform Outline Progress and Chapter Summary Closure
>
> Status: draft-v1

## 1. Purpose

Phase T exists because Phase S product QA proved that revision constraints can
reach the writer, but continuation quality is still weak when the writer only
receives a loose outline digest and local continuity text.

The missing contract is not another broad manual QA checklist. It is a product
and runtime gap:

1. accepted outlines are not materialized as stable beat records;
2. `write_next_segment` does not pin the next required beat;
3. accepted segments do not deterministically advance outline progress;
4. `complete_chapter` does not produce a stable chapter summary bridge for the
   next chapter through a replaceable provider.

Phase T closes this gap before testing stricter longform continuation behavior.

## 2. Scope

Phase T covers one coherent longform module.

### T1. Structured Outline Contract

`generate_outline` must produce or be normalized into a structured outline JSON
contract. Markdown parsing by `\n` is not the canonical source of outline
progress.

Writer-visible display text may still be Markdown, but runtime progress must
read typed beat records with stable ids.

### T2. Beat Cursor / One Segment Per Beat

One accepted story segment covers exactly one outline beat.

`write_next_segment` must include:

1. current beat id / order / title / goal;
2. required beat constraints;
3. accepted beat ids;
4. latest accepted segment excerpt;
5. instruction to write only the current beat and stop before later beats.

`accept_and_continue` advances the beat cursor only after adoption. Rewrite,
preview, selection, and unresolved comments do not advance it.

### T3. Chapter Summary Provider

`complete_chapter` must build chapter bridge material through a provider.

The first provider may use the same writer/model execution capability with a
special summary prompt, because the writer already has the necessary narrative
context. Engineering boundary:

1. the summary execution can reuse `WritingWorker` transport / model gateway;
2. the summary result is not user-visible prose output;
3. the summary is a chapter bridge Runtime Workspace sidecar;
4. the summary does not become Core / Recall / Archival truth unless a later
   governed post-write path promotes it.

`complete_chapter` remains a deterministic product action. If the first summary
provider calls an LLM, that call is provider-internal bridge maintenance, not a
new user-visible `WritingWorker` output and not a second story truth path.

This Phase T requirement intentionally strengthens the earlier lightweight
`ChapterBridgeProvider` guidance from the chapter/review adapter spec. The
implementation should extend or replace the existing chapter bridge provider
surface where practical, not create a parallel truth store or a new LLM
framework.

## 3. Non-goals

Phase T does not implement:

1. manual beat status editing;
2. automatic repair of a bad outline;
3. batch paragraph rewrite;
4. paragraph rewrite product UI / exact block replacement;
5. SuperDoc/WebView integration;
6. branch merge, physical purge, or full branch tree UI;
7. full eval runner.

Manual beat correction is a later detail-improvement slice. The current blocker
is that writer packets lack stable beat constraints.

## 4. Product Rules

1. Outline progress is runtime state, not a Markdown formatting side effect.
2. A beat is the smallest longform planning unit for this phase.
3. A segment can satisfy one beat only.
4. A beat is considered covered only after the corresponding draft is adopted.
5. A rewrite candidate can replace the segment content for a beat, but it does
   not advance the cursor until adopted.
6. Chapter completion must read adopted content and covered beats only.
7. Chapter summary material is bridge evidence, not story truth by itself.
8. Tests must assert implemented packet/provider behavior, not future manual
   editing or future paragraph-rewrite UI.

## 5. Structured Outline Contract

Recommended shape:

```json
{
  "schema_version": "longform_outline_v1",
  "chapter_index": 1,
  "chapter_title": "Chapter title",
  "chapter_goal": "What this chapter must accomplish",
  "beats": [
    {
      "beat_id": "beat_001",
      "order": 1,
      "title": "Beat title",
      "goal": "Narrative goal for this segment",
      "must_include": ["specific event", "character decision"],
      "avoid": ["spoiling later reveal"],
      "continuity_notes": ["comes after previous accepted segment"],
      "estimated_segment_role": "setup"
    }
  ],
  "constraints": {
    "tone": "optional",
    "pacing": "optional",
    "chapter_must_not_do": ["optional"]
  }
}
```

The implementation may store additional metadata, but these fields are the
minimum useful contract for beat progression.

Validation requirements:

1. `beats` must be non-empty.
2. `beat_id` must be stable within one accepted outline.
3. `order` must be unique and sortable.
4. `goal` must be non-empty.
5. invalid writer JSON must fail closed or fall back to a deterministic repair
   path that records a repair warning; it must not silently become an untracked
   Markdown-only outline.

## 6. Beat Progress Contract

Runtime should maintain a branch-scoped outline progress record:

```json
{
  "outline_artifact_id": "outline_123",
  "current_beat_id": "beat_002",
  "covered_beat_ids": ["beat_001"],
  "segment_by_beat_id": {
    "beat_001": "artifact_segment_001"
  },
  "status_by_beat_id": {
    "beat_001": "accepted",
    "beat_002": "pending"
  }
}
```

Rules:

1. `accept_outline` initializes progress from the accepted structured outline.
2. `write_next_segment` targets the first pending beat unless a later explicit
   product contract introduces manual override.
3. writer candidates must carry `target_beat_id` in artifact metadata.
4. `accept_and_continue` marks that beat accepted and advances to the next
   pending beat.
5. if no pending beat remains, the next valid longform action is
   `complete_chapter` or an explicit outline/beat repair flow that is out of
   scope for Phase T.
6. rollback / branch visibility must filter progress by active branch exactly
   like other Runtime Workspace sidecars and accepted artifacts.

## 7. Writer Packet Requirements

For `write_next_segment`, the writer packet must contain a stable
`outline_progress` or equivalent section with:

1. accepted outline ref;
2. current beat id and order;
3. current beat title, goal, must-include list, avoid list, continuity notes;
4. covered beat ids / accepted segment count;
5. latest accepted segment excerpt when present;
6. explicit instruction: write one segment for the current beat only, continue
   from the latest accepted segment, and do not write later beats.

This replaces the current weak behavior where the writer can see an outline
digest but is not bound to the next beat.

## 8. Chapter Summary Provider Boundary

Recommended interface:

```python
class ChapterSummaryProvider:
    def build_chapter_summary(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        chapter_index: int,
        accepted_outline_ref: str,
        accepted_segment_refs: list[str],
        covered_beat_ids: list[str],
    ) -> ChapterSummaryMaterial: ...
```

The concrete implementation may keep the existing `ChapterBridgeProvider` name
or adapter if that is the local owner of chapter bridge sidecars. The contract
is the provider boundary and sidecar persistence semantics, not the exact class
name.

First provider behavior:

1. assemble adopted chapter content and structured beat coverage;
2. call the writer/model gateway with a summary-specific prompt;
3. require structured summary output;
4. persist summary material with full runtime identity, branch, source refs, and
   provider metadata;
5. expose it to next chapter packet through existing chapter bridge sidecar
   rules.

The provider can be replaced later. The chapter flow must not hardcode summary
prompt text into the domain transaction.

## 9. Relation To Existing Specs

Phase T extends these existing contracts:

1. `story-runtime-writing-worker-spec.md`
   - preserves WritingWorker as the only user-visible prose writer;
   - uses writer execution capability for summary only through a provider.
2. `story-runtime-context-packet-spec.md`
   - adds structured outline progress as a writer packet section;
   - keeps bridge material as sidecar, not truth.
3. `story-runtime-longform-chapter-review-adapter-development-spec.md`
   - strengthens chapter bridge material with summary provider output;
   - keeps adoption as the only continuation base.
4. `story-runtime-product-wiring-writer-constraint-spec.md`
   - treats weak continuation as the next product blocker after S1/S2.

## 10. Acceptance Criteria

1. Accepted outline has structured beat records with stable ids.
2. `write_next_segment` writer packet identifies exactly one current beat.
3. A writer candidate records the target beat id.
4. `accept_and_continue` advances the beat cursor only after adoption.
5. Rewriting or selecting a candidate does not advance the cursor.
6. Next write targets the next pending beat and includes latest accepted prose.
7. `complete_chapter` uses adopted segments only.
8. `complete_chapter` writes chapter summary / bridge material through a
   provider boundary.
9. Next chapter packet can read the current branch's chapter bridge summary.
10. Tests do not assert manual beat editing, batch rewrite, or unimplemented UI.
