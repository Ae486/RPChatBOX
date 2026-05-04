# RP Setup Truth Index Foundation

> Executable contract for deterministic direct reads over accepted setup stage snapshots. This is a structural index over committed foundation truth, not retrieval, not embeddings, and not an agent post-commit rewrite pass.

## 1. Scope / Trigger

- Trigger: add or edit setup truth index models, services, setup read tools, setup stage commit/read tests, or setup context consumers when the change affects direct reads over committed setup truth.
- Applies to setup/prestory committed foundation truth after user accept/commit.
- Does not implement semantic retrieval, embedding materialization, graph extraction, async diagnostics, frontend rendering, or evolution editing.
- Source:
  - User-confirmed direction: after commit, the agent's work on that draft is complete; backend logic may deterministically index the accepted structured draft so later stages can locate exact facts quickly.
  - Existing stage draft contract: accepted setup truth comes from `SetupStageDraftBlock` snapshots, not raw setup discussion.
  - Existing project boundary: `setup.read.draft_refs` is for current editable draft and compact recovery; committed foundation reads need a separate source marker.

## 2. Signatures

- `SetupTruthIndexRow`
  - `source = "committed_snapshot"`
  - `workspace_id`
  - `story_id`
  - `mode`
  - `stage_id`
  - `commit_id`
  - `ref`
  - `entry_id`
  - `section_id`
  - `semantic_path`
  - `parent_path`
  - `entry_type`
  - `title`
  - `display_label`
  - `summary`
  - `aliases`
  - `tags`
  - `section_title`
  - `section_kind`
  - `retrieval_role`
  - `preview_text`
  - `content_hash`
  - `token_count`
  - `created_at`
  - `search_text`
  - `payload`
- `SetupTruthIndexFilters`
  - `stage_ids`
  - `entry_types`
  - `tags`
  - `semantic_path_prefix`
  - `commit_id`
- `SetupTruthIndexService.rebuild(workspace, commit_id=None) -> SetupTruthIndex`
- `SetupTruthIndexService.search(workspace, query, filters, limit) -> SetupTruthIndexSearchResult`
- `SetupTruthIndexService.read_refs(workspace, refs, detail, max_chars, commit_id=None) -> SetupTruthIndexReadResult`
- Read tool names:
  - `setup.truth_index.search`
  - `setup.truth_index.read_refs`

## 3. Contracts

- The index is generated from accepted commit snapshots only.
- The index must never read prior raw setup discussion.
- The index must never read uncommitted draft blocks from other stages.
- The index must never call an LLM or retrieval layer.
- Default rebuild/search/read behavior uses the latest accepted commit per canonical stage.
- Supplying `commit_id` restricts rows to that exact accepted commit.
- Search is lexical/path/filter search only:
  - title, display label, aliases, tags, semantic path, entry type, summary, section title, retrieval role, and preview text may contribute to `search_text`;
  - no vector similarity or semantic reranking is performed in this slice.
- Exact read supports committed foundation refs:
  - `foundation:<stage_id>`
  - `foundation:<stage_id>:<entry_id>`
  - `foundation:<stage_id>:<entry_id>:<section_id>`
- Exact read may also accept canonical stage refs from committed proposals as aliases:
  - `stage:<stage_id>:<entry_id>`
  - `stage:<stage_id>:<entry_id>:<section_id>`
- Search returns small candidate rows and previews only.
- Read returns bounded exact payload slices only after refs are specified.
- Every read result must identify:
  - `source = "committed_snapshot"`
  - `stage_id`
  - `commit_id`
  - `ref`
  - `found`
  - `summary`
  - `payload`
  - `truncated`
- The index is rebuildable from accepted snapshots; no persisted table is required for this MVP slice.

## 4. Validation & Error Matrix

| Condition | Boundary | Expected Handling |
| --- | --- | --- |
| No accepted canonical stage commits | service/tool | return empty search/read misses |
| Unknown stage in ref/filter | service/tool | no match, no mutation |
| Structurally invalid accepted stage snapshot | service | skip invalid snapshot for search/read and expose no rows for it |
| Query has no lexical match | search | return empty candidates |
| Ref is missing | read | return found=false and include ref in `missing_refs` |
| Payload exceeds `max_chars` | read | return bounded preview payload with `truncated=true` |
| `commit_id` does not exist | search/read | return no rows / misses |
| Editable draft has newer uncommitted changes | truth index | ignored; committed foundation truth only |

## 5. Good / Base / Bad Cases

Good:

- `world_background` commits `race_elf`; truth index search for `elf`, alias, tag, or `world_background.race` returns a committed foundation ref and preview.
- `truth_index.read_refs(["foundation:world_background:race_elf:summary"], "full")` returns the exact committed section payload with source/commit metadata.
- Rebuilding from the same accepted snapshot produces stable refs and content hashes.

Base:

- A stage has an accepted empty block. Rebuild succeeds and may produce a stage-level row without entry rows.

Bad:

- Search reads current editable `draft_blocks` instead of accepted commits.
- Search calls retrieval/embedding to find a candidate.
- Read returns raw prior-stage discussion.
- Agent rewrites committed JSON after commit to improve the index.

## 6. Tests Required

- Service tests:
  - rebuild from accepted stage snapshot produces stage/entry/section rows.
  - search matches title, alias, tag, and semantic path.
  - read by committed foundation ref returns exact bounded payload and source metadata.
  - default index uses the latest accepted commit per stage.
  - explicit `commit_id` can read an older accepted commit.
- Tool tests:
  - `setup.truth_index.search` returns candidate refs and previews.
  - `setup.truth_index.read_refs` reads exact committed refs and reports misses.
  - these tools do not read current uncommitted draft changes.

## 7. Wrong vs Correct

Wrong:

- Treat Setup Truth Index as a second RAG.
- Persist a new mutable truth table before the deterministic model shape is proven.
- Make the agent fix committed setup truth after commit.
- Reuse `setup.read.draft_refs` and hide whether data came from editable draft or committed foundation.

Correct:

- Rebuild deterministic rows from accepted snapshots.
- Keep search lexical/filter/path only.
- Keep exact read separate from search.
- Preserve commit/stage/entry/section anchors so retrieval and future evolution can point back to the same committed source.
