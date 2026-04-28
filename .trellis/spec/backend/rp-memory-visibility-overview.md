# RP Memory Visibility Overview

## Scenario: Active story memory has a read-only overview that makes layer capabilities and boundaries visible without adding new mutation paths

### 1. Scope / Trigger

- Trigger: the memory layer now has several real read-side surfaces, but their capabilities are spread across Core State reads, Block views, proposal visibility, Runtime Workspace views, and consumer dirty state.
- Applies to RP backend implementation across:
  - `StoryRuntimeController` memory read-side facade;
  - `/api/rp/story-sessions/{session_id}/memory/overview`;
  - existing `RpBlockReadService`, `MemoryInspectionReadService`, and optional `StoryBlockConsumerStateService` outputs;
  - focused controller/API tests.
- This slice does **not** query retrieval-core for Recall/Archival counts.
- This slice does **not** create a durable `rp_blocks` registry.
- This slice does **not** add mutation support, proposal apply exposure, or agent-facing block edit tools.

### 2. Surface

Controller surface:

```python
def read_memory_overview(*, session_id: str) -> dict:
    ...
```

API surface:

```text
GET /api/rp/story-sessions/{session_id}/memory/overview
```

Representative response shape:

```json
{
  "session_id": "session_123",
  "story_id": "story_123",
  "current_chapter_index": 1,
  "current_phase": "segment_drafting",
  "blocks": {
    "total": 8,
    "by_layer": {
      "core_state.authoritative": 3,
      "core_state.projection": 4,
      "runtime_workspace": 1
    },
    "by_source": {
      "core_state_store": 5,
      "compatibility_mirror": 2,
      "runtime_workspace_store": 1
    }
  },
  "layers": {
    "core_state.authoritative": {
      "semantic_layer": "Core State.authoritative_state",
      "block_count": 3,
      "mutation": "governed_proposal_apply",
      "history": "supported",
      "truth_status": "authoritative_truth"
    },
    "runtime_workspace": {
      "semantic_layer": "Runtime Workspace",
      "block_count": 1,
      "mutation": "unsupported_read_only",
      "history": "unsupported",
      "truth_status": "current_turn_scratch"
    }
  },
  "proposals": {
    "total": 2,
    "by_status": {
      "review_required": 1,
      "applied": 1
    }
  },
  "consumers": {
    "total": 3,
    "dirty": 3,
    "items": []
  },
  "boundaries": [
    "runtime_workspace_blocks_are_read_only",
    "recall_and_archival_are_retrieval_backed_not_block_native",
    "authoritative_mutation_requires_proposal_apply"
  ]
}
```

### 3. Contracts

- Read-only aggregation:
  - overview must reuse existing read services;
  - overview must not mutate session, block, proposal, consumer, retrieval, or Core State records;
  - overview must not mark consumers synced or compiled.
- Boundary visibility:
  - Core State authoritative must be reported as governed mutable through proposal/apply;
  - Core State projection must be reported as maintenance/read-side projection, not authoritative truth;
  - Runtime Workspace must be reported as read-only current-turn scratch with unsupported history/provenance/proposal semantics;
  - Recall and Archival must be reported as retrieval-backed surfaces, not Block-native durable stores.
- Count semantics:
  - block counts come from current `RpBlockReadService.list_blocks(...)`;
  - proposal counts come from current session proposals only;
  - consumer dirty counts come from `StoryBlockConsumerStateService.list_consumers(...)` when configured, and empty counts otherwise;
  - this slice does not compute Recall/Archival item counts because the story runtime controller currently has no retrieval-core read dependency.
- Compatibility:
  - existing `/memory/authoritative`, `/memory/projection`, `/memory/blocks`, `/memory/proposals`, `/memory/versions`, `/memory/provenance`, and `/memory/block-consumers` responses stay unchanged;
  - missing session behavior matches existing memory routes.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Existing Core State store + Runtime Workspace blocks exist | Overview reports block counts by layer/source |
| Review/applied proposals exist for the session | Overview reports proposal counts by status |
| Consumer registry is configured | Overview reports consumer total/dirty counts without changing sync state |
| Consumer registry is absent | Overview returns zero consumers rather than failing |
| Runtime Workspace block exists | Overview marks Runtime Workspace mutation/history as unsupported read-only |
| Recall/Archival are present only as retrieval-backed capabilities | Overview marks them as retrieval-backed and count-unavailable |
| Session does not exist | API returns the existing `story_session_not_found` error shape |

### 5. Tests Required

- Controller test:
  - overview reports Core State, Runtime Workspace, proposal, and consumer boundary counts from existing services;
  - overview does not mark consumers synced.
- API test:
  - `/memory/overview` returns the same session-scoped envelope and missing-session behavior as other memory read routes.

### 6. Wrong vs Correct

#### Wrong

```python
# Wrong: make overview synchronize consumers as a side effect.
consumer_service.mark_consumer_synced(session_id=session_id, consumer_key="story.specialist")
```

#### Correct

```python
# Correct: list current consumer state and report dirty status only.
consumers = consumer_service.list_consumers(session_id=session_id)
```

## Status on 2026-04-28

- Planned as the next memory-layer-only slice after the capability review concluded that the remaining high-end Block runtime features depend on upstream product/runtime semantics.
