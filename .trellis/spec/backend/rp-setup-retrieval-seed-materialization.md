# RP Setup Retrieval Seed Materialization

> Executable contract for deterministic retrieval seed sections derived from accepted setup stage entry/section trees.

## 1. Scope / Trigger

- Trigger: add or edit `backend/rp/services/minimal_retrieval_ingestion_service.py`, setup accepted-commit ingestion jobs, retrieval seed-section metadata, setup stage draft entry/section rendering, or focused ingestion tests when the change affects post-commit setup materialization into retrieval-core.
- Applies after a setup stage draft is accepted/committed.
- This is a retrieval materialization slice. It does not change SetupAgent behavior, does not change editable draft reads, does not add semantic retrieval tools, and does not add a new persisted truth table.
- Source:
  - User-confirmed product boundary: after commit, the agent's work on that draft is complete; backend/retrieval logic may deterministically materialize accepted structured draft content.
  - Existing setup draft contract: LLM/user produce `SetupStageDraftBlock -> SetupDraftEntry -> SetupDraftSection` before commit.
  - Existing retrieval-core behavior: `seed_sections` are parsed by `Parser`, then `Chunker` already performs section-aligned paragraph/fixed-window primary splits plus optional secondary sliding-window chunks.
  - Project adaptation: keep setup materialization lightweight and exact; no post-commit LLM rewrite.

## 2. Signatures

- `MinimalRetrievalIngestionService._build_sections(...) -> list[dict[str, object]]`
  - for canonical setup stage snapshots, return one retrieval seed section per renderable setup draft section;
  - when an entry has no renderable sections, return one entry-level fallback seed section.
- Seed section shape:
  - `section_id: str`
  - `title: str`
  - `path: str`
  - `level: int`
  - `text: str`
  - `metadata: dict`
- Required setup anchor metadata on stage-derived seed sections:
  - `stage_id`
  - `entry_id`
  - `entry_type`
  - `entry_title`
  - `entry_domain_path`
  - `semantic_path`
  - `section_id`
  - `section_title`
  - `section_kind`
  - `retrieval_role`
  - `section_semantic_path`
  - `committed_ref`
  - `stage_ref`
- Existing canonical archival metadata remains required:
  - `layer = "archival"`
  - `source_family = "setup_source"`
  - `source_type`
  - `import_event = "setup.commit_ingest"`
  - `workspace_id`
  - `commit_id`
  - `step_id`
  - `source_ref`
  - `domain`
  - `domain_path`

## 3. Contracts

- Materialization reads only `SetupAcceptedCommitRecord.snapshot_payload_json`.
- Materialization must not read editable `SetupWorkspace.draft_blocks`.
- Materialization must not read raw setup discussion history.
- Materialization must not call an LLM.
- Canonical stage snapshots are detected by block keys that coerce to `SetupStageId`.
- For canonical stage entries:
  - entry semantic path remains the parent anchor, e.g. `world_background.race.elf`;
  - child setup sections become retrieval seed sections, e.g. `world_background.race.elf.summary`;
  - every child seed section preserves parent entry metadata.
- SourceAsset-level `domain_path` should stay entry-level when available, so the asset represents the committed setup entry.
- KnowledgeChunk-level `domain_path` should be section-level when the setup section is materialized, because retrieval should be able to target exact entry sections.
- Oversized section text should rely on retrieval-core chunking:
  - setup materialization emits the full section text once;
  - `Chunker` mechanically splits by paragraph/fixed-window primary slices and optional secondary sliding windows;
  - setup materialization must not semantically rewrite or summarize oversized text.
- Legacy foundation entries without `sections` keep the existing entry-level fallback behavior.
- Retrieval materialization status remains asynchronous and non-blocking for setup stage progression and commit warnings.

## 4. Validation & Error Matrix

| Condition | Boundary | Expected Handling |
| --- | --- | --- |
| No accepted commit | ingestion caller | existing accepted-commit lookup error |
| Commit snapshot has no target entry | materialization | return no seed sections for that job |
| Canonical stage entry has renderable sections | materialization | return one seed section per renderable section |
| Canonical stage entry has no sections | materialization | return one entry-level fallback seed section |
| Section content is empty or unsupported | materialization | skip that section; if all sections skip, use entry-level fallback when possible |
| Oversized section | retrieval-core chunker | deterministic mechanical chunks with setup anchors preserved |
| Retrieval/graph queue fails | ingestion | diagnostics/warnings only; committed snapshot remains unchanged |
| Editable draft changed after commit | materialization | ignored |

## 5. Good / Base / Bad Cases

Good:

- `world_background.race.elf` has `summary` and `customs` sections. Ingestion creates two seed sections with `entry_id=race_elf`, section-level domain paths, and refs such as `foundation:world_background:race_elf:customs`.
- A long setup section is emitted as one seed section, then retrieval-core creates multiple chunks while preserving `entry_id`, `section_id`, `committed_ref`, and `stage_ref` in chunk metadata.

Base:

- A legacy `foundation` entry with only `content` still materializes as one entry-level seed section.

Bad:

- Flattening every child section into one giant entry-level seed section.
- Calling the agent or another LLM after commit to rewrite setup draft into retrieval chunks.
- Using uncommitted draft blocks as retrieval source material.
- Blocking the next setup stage because retrieval materialization is still queued.

## 6. Tests Required

- `backend/rp/tests/test_minimal_retrieval_ingestion_service.py`
  - canonical stage entry with multiple sections produces multiple seed sections and chunks with section-level paths;
  - child section chunks preserve parent entry metadata and committed/stage refs;
  - oversized setup section is mechanically split by retrieval-core and preserves setup anchors on all produced chunks;
  - legacy foundation entry ingestion remains entry-level compatible.

## 7. Wrong vs Correct

Wrong:

- Treat setup materialization as another agent loop.
- Store only one coarse entry chunk even when the accepted draft already has stable child sections.
- Move retrieval readiness into setup commit gating.

Correct:

- Trust the accepted setup JSON as the semantic tree.
- Generate deterministic seed sections from entry/section structure.
- Let retrieval-core do mechanical chunk splitting.
- Keep all source anchors visible so future diagnostics, truth-index reads, and evolution workflows can point back to the committed setup source.
