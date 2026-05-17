# Confirmed SetupAgent Session Memory Implementation Plan

Date: 2026-05-13

Status: Superseded by [`setup-agent-memory-redesign-plan-2026-05-16.md`](setup-agent-memory-redesign-plan-2026-05-16.md).

This document preserves the first confirmed implementation slice. The current confirmed workflow has changed from `search + read_refs` to `search + open`:

```text
agent-visible level-3 session index
  -> setup.memory.search when the ref is unknown
  -> setup.memory.open(level-3 entry ref) returns level-4 section directory
  -> setup.memory.open(level-4 section ref) returns clean structured content
```

`setup.memory.read_refs` is compatibility/internal only while older tests and paths are migrated.

## Confirmed Scope

SetupAgent memory is a session-scoped retrieval subsystem whose lifecycle matches one `SetupWorkspace` / setup discussion session. It exists to recover exact setup draft and setup-session details after long discussion, stage-local compaction, cross-stage transitions, and large structured draft growth.

It is not:

- Claude Code style cross-project user/profile memory.
- RP Memory OS / Recall / Archival / GraphRAG.
- `SetupWorkspace` business truth.
- `SetupAgentRuntimeStateService` state expansion.
- A file-backed primary store.

The correct architecture is:

```text
SetupAgent internal memory subsystem
  -> manifest/source/freshness/search/open/read services
  -> exposed to the model through read-only setup tools
     setup.memory.search
     setup.memory.open
```

Memory is an agent capability, not agent state. Tools are the controlled interface through which the model uses that capability.

## Why This Matches The Current Agent Architecture

The current SetupAgent stack already separates:

- `SetupContextBuilder`: reads `SetupWorkspace` truth.
- `SetupContextGovernor`: compacts current-step history and produces recovery hints.
- `SetupRuntimeAdapter`: builds prompt/context/tool scope.
- `SetupCapabilityPlan`: decides which tools are visible for a turn.
- `RpAgentRuntimeExecutor`: runs model/tool/observe/guard loop.
- `SetupToolProvider`: owns deterministic setup tool execution.
- `SetupAgentRuntimeStateService`: persists runtime-private cognition only.

Session memory should not be folded into any one of those files. It should be a detachable subsystem used by tool adapters and later optionally by context/prefetch policy.

## Claude Code / pi-mono Lessons Applied

Claude Code lesson:

- memory is a separate subsystem with index/manifest, selector, freshness, top-k bounds, and already-surfaced/session-budget controls;
- it is not a generic RAG or vector DB;
- recovered content is lower-authority than current project truth and must be verified against live sources.

pi-mono lesson:

- context/tools are selected into the agent loop rather than hardwired into core state;
- context transform happens before model call;
- tools are capabilities in the current agent context, not global exposure.

Project-specific adaptation:

- because setup drafts and accepted setup truth are DB-backed structured JSON, the source manifest is derived from setup fact sources: editable draft and accepted truth;
- editable draft and accepted truth are the same kind of agent-facing recall material for this feature: both are established setup facts, normalized into the same folder-like index/open workflow;
- compact summaries, recovery hints, and handoffs are context-layer artifacts, not memory index/open sources;
- exact details are read from current DB-backed payloads through `setup.memory.open`;
- no file-backed primary memory store in MVP.

## MVP Slice

Implement a modular `backend/rp/setup_agent_memory/` package:

```text
contracts.py
fingerprints.py
sources.py
draft_source.py
truth_source.py
manifest_builder.py
scorer.py
reader.py
service.py
```

Tool adapters stay thin:

```text
backend/rp/tools/setup_tools/memory_search.py
backend/rp/tools/setup_tools/memory_open.py
```

Registry/profile changes:

- register `setup.memory.search`;
- register `setup.memory.open`;
- include both in the read-only setup tool scope through `SetupCapabilityPlan`;
- keep `setup.memory.read_refs` only as compatibility/internal readback where still required.

## Data Flow

```text
SetupWorkspace editable draft + accepted setup truth
  -> SetupSessionMemoryManifest
  -> setup.memory.search(query, filters)
  -> SetupSessionMemoryHit refs
  -> setup.memory.open(ref)
  -> level-3 section directory or level-4 clean structured content from current source
```

Search must not return large payloads. It returns refs, paths, titles, scopes, deterministic navigation messages, and bounded `navigation_summary` values only. Debug metadata such as source kind, score, reason, and freshness may exist internally but should not be part of the default agent-facing payload.

## Storage

MVP does not add a persistent table.

The manifest is rebuildable from current setup records:

- `rp_setup_draft_blocks.payload_json`;
- accepted setup commit snapshots via `SetupTruthIndexService`.

If a later performance slice needs caching, add a setup-specific SQLModel cache table that stores only refs/metadata/fingerprints, never duplicate full draft payload.

## First Implementation Slice Acceptance

- New modular package exists and is importable.
- Manifest builder returns stable refs for editable draft and accepted truth entry/section rows.
- Search returns deterministic top-k hits over refs/title/summary/path/tags/stage metadata.
- Open can read known refs through current sources and reports missing refs without mutation.
- Focused tests cover manifest generation, search scoring, open missing/bounded behavior, clean content shape, and freshness metadata.
- No RP Memory OS or story runtime behavior changes.
