# RP Setup Agent Action Decision Policy

> Historical contract for a lightweight SetupAgent action-decision policy.

Status: Superseded for SetupAgent memory recall.

Do not implement new memory-specific `SetupActionExpectation`, `ActionDecisionPolicy`, completion-guard, or tool-batch blocking behavior from this file.

The current memory recall design is owned by [RP Setup Agent Session Memory](./rp-setup-agent-session-memory.md):

```text
agent-visible level-3 session index
  -> setup.memory.search when the ref is unknown
  -> setup.memory.open(level-3 entry ref) returns level-4 section directory
  -> setup.memory.open(level-4 section ref) returns clean structured content
```

`setup.memory.read_refs` is compatibility/internal only while older tests and paths are migrated.

## Superseded Behavior

The former design tried to infer missing exact setup details in runtime policy and then force a `search -> read` chain through completion guards and tool-batch blocking. That direction is no longer accepted because it moves agent cognition into brittle backend policy code.

The accepted direction is:

- no memory-specific action expectation;
- no memory keyword classifier;
- no completion guard that blocks finalization only because memory search/read was not performed;
- no tool-batch blocking that forces memory search/read before other actions;
- agent prompt/context guidance tells the model that index rows and summaries are navigation only;
- deterministic `setup.memory.open` results tell the model whether it received a directory or usable fact content.

Runtime guards may still exist for deterministic failures, such as invalid tool output, repair obligations, repeated no-progress loops, and commit/readiness rules. They should not reintroduce a semantic memory-recall classifier.

## Current Tests Should Assert

- memory recall uses `setup.memory.search` + `setup.memory.open` as the recommended model-facing chain;
- `setup.memory.open` on a level-3 entry ref returns a level-4 section directory, not full content;
- `setup.memory.open` on a level-4 section ref returns clean structured content;
- `setup.memory.read_refs` remains compatible only where older paths still require it;
- runtime policy does not force memory recall through `SetupActionExpectation`, `ActionDecisionPolicy`, completion guard, or tool-batch blocking.
