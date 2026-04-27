# RP Memory Tool Chain Block Compatibility

## Scenario: Public memory tool contracts stay stable after Core State Block integration

### 1. Scope / Trigger

- Trigger: Core State reads are now Block-backed in several places, and the repo needs a compatibility gate to ensure the retrieval/tool chain still works.
- Applies to:
  - `RetrievalBroker`
  - `MemoryOsService`
  - `MemoryCrudToolProvider`
  - focused provider-facing tests
- This slice is a compatibility/usability gate, not a new feature family.

### 2. Contracts

- `MemoryOsService` remains a facade over `RetrievalBroker`.
- `MemoryCrudToolProvider` keeps the same public tool names:
  - `memory.get_state`
  - `memory.get_summary`
  - `memory.search_recall`
  - `memory.search_archival`
  - `proposal.submit`
  - `memory.list_versions`
  - `memory.read_provenance`
- The provider must not call Block services directly.
- `memory.get_state` must still serialize canonical JSON correctly when the broker repairs explicit refs through Block fallback.
- `memory.get_summary` must still serialize canonical JSON correctly when the broker enriches or fulfills results from projection Blocks.
- `memory.list_versions` and `memory.read_provenance` must keep their canonical JSON shape when the target ref resolves against formal Core State history/provenance.
- `proposal.submit` must keep returning the canonical proposal receipt shape and must not introduce Block-specific branching in the provider.
- Existing routing through `LocalToolProviderRegistry` / `McpManager` must remain valid after Block-backed read enrichment.

### 3. Tests Required

- Provider returns canonical JSON for explicit authoritative ref reads that are fulfilled through Block fallback.
- Provider returns canonical JSON for projection summary reads that include Block metadata.
- Provider returns canonical JSON for `memory.list_versions` and `memory.read_provenance` over formal authoritative history.
- Provider returns canonical JSON for successful `proposal.submit` receipts and persists the submitted input unchanged.
- Existing registry/MCP routing remains valid.
- Existing validation / error contract remains stable.

### 4. Boundary Rules

- Do not add new public tool names in this slice.
- Do not move Block fallback logic from `RetrievalBroker` into the provider.
- Do not change retrieval recall / archival semantics in this slice.
- Use focused tests to validate compatibility rather than broad full-repo checks.

### 5. Wrong vs Correct

#### Wrong

```python
# Wrong: adapt the provider by bypassing RetrievalBroker and serializing Block views directly.
return serialize_result(rp_block_read_service.list_blocks(session_id=session_id))
```

#### Correct

```python
# Correct: keep the provider contract stable and validate that the Block-backed
# RetrievalBroker output still serializes cleanly through the existing path.
result = await memory_os_service.get_summary(input_model)
return serialize_result(result)
```
