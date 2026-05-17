# RP Setup Agent Session Memory

> Executable contract for SetupAgent session-scoped memory retrieval: a detachable internal subsystem that builds a rebuildable manifest over current setup sources and exposes read-only `setup.memory.*` tools to the model.

## Scenario: SetupAgent Recovers Exact Setup Details Through Session Memory Refs

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/setup_agent_memory/*`, `backend/rp/tools/setup_tools/memory_*.py`, setup tool registry/provider wiring, or `SetupCapabilityPlan` read-only setup tools.
- Applies only to SetupAgent / prestory setup discussion sessions.
- The subsystem lifecycle matches one `SetupWorkspace` / setup discussion session.
- This is not RP Memory OS, Recall, Archival, GraphRAG, retrieval-core, or long-term user/project preference memory.
- SetupAgent does not directly expose external Memory OS read-only tools such as `memory.get_state`, `memory.get_summary`, `memory.search_recall`, `memory.search_archival`, `memory.list_versions`, or `memory.read_provenance`; it uses only setup-owned `setup.memory.*` tools for this subsystem.
- This is not a `SetupWorkspace` truth store and not a `SetupAgentRuntimeStateService` state expansion.
- MVP storage is rebuildable from DB-backed setup records; no persistent table or file-backed primary store is introduced.

### 2. Signatures

- Package:
  - `backend/rp/setup_agent_memory/contracts.py`
  - `fingerprints.py`
  - `sources.py`
  - `draft_source.py`
  - `truth_source.py`
  - `manifest_builder.py`
  - `scorer.py`
  - `reader.py`
  - `service.py`
- `SetupSessionMemorySourceKind`
  - `editable_draft`
  - `accepted_truth`
- `SetupSessionMemoryRefKind`
  - `setup_fact_entry`
  - `setup_fact_section`
- `SetupSessionMemoryManifestItem`
  - `ref`
  - `title`
  - `summary`
  - `source_kind`
  - `ref_kind`
  - `stage`
  - `block_type`
  - `tags`
  - `search_text`
  - `freshness`
  - `metadata`
- `SetupSessionMemorySearchInput`
  - `workspace_id: str`
  - `query: str = ""`
  - `filters: SetupSessionMemorySearchFilters`
  - `limit: int = 10`
- `SetupSessionMemoryHit`
  - `ref`
  - `title`
  - `path`
  - `scope: Literal["entry", "section", ...]`
  - `navigation_summary`
  - `message`
- Internal search/debug records may also carry `source_kind`, `ref_kind`, `stage`, `block_type`, `score`, `reason`, and `freshness`, but those fields are not part of the default agent-facing hit payload.
- `SetupSessionMemoryReadInput`
  - `workspace_id: str`
  - `refs: list[str]`
  - `detail: Literal["summary", "full"] = "summary"`
  - `max_chars: int = 4000`
- `SetupSessionMemoryOpenInput`
  - `workspace_id: str`
  - `ref: str`
  - `max_chars: int = 4000`
- `SetupSessionMemoryOpenResult`
  - `success: bool`
  - `result_type: Literal["index", "content", "error"]`
  - `opened_ref: str`
  - `opened_path: str`
  - `message: str`
  - `sections: list[CleanSectionIndexItem] | None`
  - `content: CleanSectionContentBlock | None`
  - `truncated: bool = false`
- `SetupSessionMemoryContentBlock`
  - `type: Literal["text", "list", "key_value", "truncated", "unknown"]`
  - `title: str | None`
  - `text: str | None`
  - `items: list[Any] | None`
  - `values: dict[str, Any] | None`
  - `preview: str | None`
- Setup tools:
  - `setup.memory.search`
  - `setup.memory.open`
  - `setup.memory.read_refs`

### 3. Contracts

- `SetupAgent memory` is an internal SetupAgent capability. The model uses it only through read-only setup tools unless a later spec adds bounded prefetch.
- The memory index/open source set is setup facts only. Editable draft and accepted truth are both setup fact sources and should be normalized into the same agent-facing folder-like index/open workflow.
- Handoff packets, runtime compact summaries, and recovery hints belong to context assembly / compaction recovery. They are not memory index/open sources and should not produce agent-facing `setup.memory.search` hits.
- Search builds a manifest from current setup sources:
  - editable current draft entries / sections from `SetupWorkspace`;
  - accepted setup truth entries / sections via `SetupTruthIndexService` or equivalent current truth source.
- Search returns small candidate hits only. It must never return full payload blobs.
- Search hit `navigation_summary` must be bounded and must be treated as navigation aid only, not fact evidence. Long source summaries are truncated before entering the hit.
- `setup.memory.open` is the recommended agent-facing exact recall surface:
  - it opens exactly one ref per call in the first slice;
  - opening a level-3 entry ref returns `result_type="index"` with clean level-4 section refs, titles, paths, and optional `navigation_summary`;
  - opening a level-4 section ref returns `result_type="content"` with clean structured content;
  - opening a level-3 entry ref must not return full entry content in the first slice;
  - the result must include a deterministic `message` that tells the model whether it received a directory/index or usable fact content.
- Level-3 entry open is a directory view. Every returned section `navigation_summary` is bounded and remains navigation-only. It may help the model choose the next section ref, but it must not become the final factual answer.
- Level-4 section open is a clean content view. The reader must first convert source payload into an agent-facing `text` / `list` / `key_value` content block, then apply `max_chars` to that clean content. It must not truncate raw source payload JSON and return that JSON as a fallback preview.
- Truncated or unknown section content must remain clean:
  - bounded `text` content may be returned with `truncated=true`;
  - oversized list/key-value content may return a `truncated` block with a preview derived from the effective content, not the raw payload envelope;
  - payload envelopes and internal fields such as `section_id`, `retrieval_role`, `source_kind`, `ref_kind`, `fingerprint`, `freshness`, `score`, or `reason` must not appear in agent-facing open output.
- `setup.memory.read_refs` is a compatibility/internal readback surface during transition:
  - editable draft refs dispatch through internal draft-ref reader semantics;
  - accepted truth refs dispatch through `SetupTruthIndexService.read_refs`;
  - missing refs return `found=false` and appear in `missing_refs`.
- Freshness is metadata, not authority. Internal records may include workspace version and source fingerprint so runtime/debug surfaces can reason about staleness, but default agent-facing search/open payloads should not expose freshness/debug fields.
- `SetupCapabilityPlan` is the only model-visible tool-scope authority. Registering `setup.memory.*` in the provider registry is not enough; they must be present in the active read-only setup tool scope.
- `SetupCapabilityPlan` must keep `setup.memory.search` and `setup.memory.open` visible to SetupAgent while excluding external Memory OS read-only tools.
- `setup.memory.read_refs` may remain registered or allowlisted for compatibility, but prompt guidance must make `setup.memory.search` + `setup.memory.open` the main agent workflow.
- The subsystem must stay modular. Source adapters, manifest build, scoring, exact reading, and setup tool adapters must remain separable.

### 4. Validation & Error Matrix

| Condition | Expected Handling |
| --- | --- |
| Workspace is missing | provider returns normal setup tool failure through existing provider error path |
| Manifest has no hits | search returns `success=true`, `items=[]` |
| Query is empty | search may return deterministic top refs with low reason such as `empty_query` |
| Search hit source summary is long | `navigation_summary` is truncated to the configured small-preview bound |
| Entry open section summary is long | section `navigation_summary` is truncated to the directory-preview bound |
| Ref is absent from manifest | `open` returns a normal clean failure for the single ref; compatibility `read_refs` returns `found=false` and includes the ref in `missing_refs` |
| `open.ref` is a level-3 entry ref | returns `result_type="index"` and section refs only, no full section content |
| `open.ref` is a level-4 section ref | returns `result_type="content"` and a clean structured content block |
| `open.ref` points to block/stage/root scope | returns a clean failure explaining that `open` expects a level-3 entry ref or level-4 section ref |
| `read_refs.refs` is empty | tool raises `setup_memory_refs_required` validation-style error |
| Section payload exceeds `max_chars` | `open` returns bounded clean content and `truncated=true`; it does not expose the raw payload envelope |
| Section payload is missing or malformed | `open` returns a clean `unknown`/`truncated` block or clean failure; it does not echo raw payload JSON |
| Editable draft changes between turns | manifest is rebuilt from current workspace state; stale copied payload is not used |
| RP Memory OS / retrieval-core would be needed | invalid for this contract; use setup sources only |

### 5. Good / Base / Bad Cases

Good:

- A compacted setup turn needs an exact world-background detail. The model calls `setup.memory.search`, receives a candidate such as `stage:world_background:race_elf:habitat`, then calls `setup.memory.open` before answering.
- A visible level-3 index already contains `stage:world_background:race_elf`. The model calls `setup.memory.open` once, receives the level-4 section directory, then opens the relevant section ref.
- Search returns `ref`, `path`, `title`, `scope`, `navigation_summary`, and a deterministic navigation message, but no source payload or debug metadata.
- Open of an editable draft or accepted truth section uses the current source payload but returns only clean agent-facing content.
- Open of a long section returns the bounded clean `text`/`list`/`key_value` content or a clean `truncated` block. The returned JSON does not contain payload-envelope or debug fields.

Base:

- No matching refs exist; search returns an empty list and the normal setup conversation continues.
- Context compact / handoff artifacts may still appear in context-layer guidance, but they are not memory search/open hits.

Bad:

- Storing a duplicate full draft copy inside a new memory table or file directory.
- Using RP Memory OS / Recall / Archival / GraphRAG to recover editable setup draft truth.
- Adding `setup.memory.*` to provider registration but forgetting `SetupCapabilityPlan`, leaving prompt guidance and runtime allowlist inconsistent.
- Returning full payloads from search because the model might need them.
- Returning full entry content from `setup.memory.open(stage:<stage>:<entry_id>)`; level-3 open must return the fourth-level directory.
- Returning raw payload JSON from `setup.memory.open` when content is oversized or unknown.
- Leaking `section_id`, `retrieval_role`, source kind, ref kind, fingerprint, score, or freshness into agent-facing search/open output.
- Extending `SetupAgentRuntimeStateService.snapshot_json` with manifest/search rows.

### 6. Tests Required

- Manifest tests:
  - editable draft entry / section refs are generated;
  - accepted truth entry / section refs are generated where accepted truth is available;
  - editable draft and accepted truth refs normalize to the same agent-facing folder tree;
  - handoff / runtime compact / recovery refs are not generated as memory index/open items;
  - freshness contains workspace version and fingerprint;
  - manifest source kinds stay within setup-session source kinds.
- Search tests:
  - deterministic lexical scoring returns relevant top refs;
  - filters by stage/source/ref kind work;
  - search hits do not contain payload;
  - long `navigation_summary` values are bounded;
  - candidates may include section-level refs when section content is the strongest match.
- Open tests:
  - level-3 entry refs return `result_type="index"` with section refs and no full content;
  - level-3 entry directory section summaries are bounded;
  - level-4 section refs return `result_type="content"` with clean structured blocks;
  - open only accepts one ref per call;
  - unsupported block/stage/root refs return clean failures;
  - editable draft and accepted truth refs read exact current payload through the internal reader path;
  - accepted truth section open uses the same clean content shape as editable draft section open;
  - missing refs are reported;
  - oversized content is bounded by `max_chars`;
  - truncated/unknown content does not leak internal payload-envelope fields.
- Tool tests:
  - `setup.memory.search` and `setup.memory.open` are registered;
  - `setup.memory.read_refs` remains compatible where still required;
  - provider schema map and dispatch handlers stay aligned;
  - search/open appear in `SetupCapabilityPlan.runtime_allowlist`.
  - external Memory OS read-only tools do not appear in SetupAgent runtime allowlists, prompt guidance, or model request schemas.

### 7. Wrong vs Correct

#### Wrong

- Treat session memory as a new durable truth store.
- Put memory rows into `SetupAgentRuntimeStateRecord.snapshot_json`.
- Copy Claude Code's file-backed long-term user memory as the SetupAgent draft recovery store.
- Let search results carry exact draft payloads.
- Route setup memory reads through RP Memory OS or retrieval-core.
- Use raw payload JSON as the fallback preview for oversized `open` content.

#### Correct

- Treat memory as a SetupAgent internal retrieval subsystem with read-only model tools.
- Rebuild the manifest from live setup sources each time.
- Return only small search hits from `setup.memory.search`.
- Use `setup.memory.open` for exact details.
- Treat `setup.memory.search` and index summaries as navigation only.
- Clean the section payload into agent-facing content before bounding or truncating it.
- Keep compatibility `read_refs` aligned with clean-view rules if it remains model-visible.
- Keep provider registration, prompt guidance, and runtime allowlist aligned through `SetupCapabilityPlan`.
