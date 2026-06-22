# S3a Implementation Brief — Registry And Candidate Contracts

Status: ready for implement worker
Date: 2026-06-23

## Mission

Implement the S3a slice only:

```text
runtime longform memory contract registry
  + memory maintenance candidate DTOs
  + deterministic candidate validator
  + focused unit/service tests
```

Do not implement worker model execution, tool loop, proposal workflow, apply, or
maintenance lock behavior in S3a. Those belong to later S3b/S3c/S3d slices.

## Required Reading

Read these before editing code:

- `execution/phase-5-implementation/S3/01-PRD.md`
- `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md`
- `execution/phase-5-implementation/S3/03-test-and-gate-plan.md`
- `execution/phase-5-implementation/S3/review-record.md`
- `execution/phase-5-implementation/S3/05-main-brain-adjudication.md`
- `research/modules/runtime-memory-domain-block.md`
- `research/modules/runtime-worker-family.md`
- `research/story-runtime-stage-w5-scheduler-layer-development-spec.md`
- `research/story-runtime-memory-domain-block-worker-discussion.md`
- `execution/phase-1-spec-freeze/acceptance-criteria.md`

Use YCE for codebase search. Do not use ACE.

## Current Code Evidence

YCE and direct reads show existing memory registry code here:

- `backend/rp/services/memory/contract_registry.py`
- `backend/rp/models/memory/contract_registry.py`
- `backend/rp/services/memory/registry_management_service.py`
- `backend/rp/tests/services/memory/test_memory_contract_registry.py`

Important current-state finding:

- The existing bootstrap registry is the old broad Memory OS foundation with 13
  domains (`scene`, `character`, `knowledge_boundary`, `relation`, etc.).
- S3 longform must not treat that old domain set as authoritative.
- W5/S3 longform Core requires exactly five domains:
  - `current_scene`
  - `character_state`
  - `knowledge_state`
  - `plot_threads`
  - `world_constraints`

Therefore, do not blindly replace shared legacy registry behavior unless tests
prove no regression. Prefer a clear S3 longform runtime registry surface or
adapter that can coexist with current bootstrap registry code.

## Required S3 Longform Topology

Exact domain set:

```text
current_scene
character_state
knowledge_state
plot_threads
world_constraints
```

Exact first-pass block ids:

```text
current_scene:
  - scene.frame
  - scene.pressure
  - scene.bridge

character_state:
  - character.current_state
  - character.intent
  - character.relationships

knowledge_state:
  - knowledge.by_subject
  - knowledge.secrets_reveals

plot_threads:
  - plot.active_threads
  - plot.foreshadow_payoff
  - plot.causal_spine

world_constraints:
  - world.rules
  - world.resources
```

Field shape:

```text
optional group / collection
  -> facts[]
```

Workers may append/update/remove fact items or subject groups inside declared
blocks. Workers must not create/delete domains, create/delete blocks, or change
block schema.

## Candidate Contract Requirements

Add S3 memory maintenance candidate contracts. Exact class names are engineering
choice, but the semantics are not.

Required candidate batch fields:

- `schema_version`
- `worker_id`
- `phase`
- `candidates[]`

Required candidate fields:

- `target_domain`
- `target_block_id` or explicit target block ref
- `base_block_revision_id`
- `operations[]`
- `source_refs[]`
- `change_summary`

Required operation semantics:

- support first-slice operations:
  - `append_item`
  - `update_item`
  - `remove_item`
- reject:
  - create/delete domain;
  - create/delete block;
  - schema change;
  - unsupported operation;
  - unknown target domain/block;
  - missing source refs;
  - missing base revision;
  - contradictory operations on the same fact in one candidate.

Candidate DTOs must be strict enough that unknown extra fields do not silently
become accepted semantics.

## Suggested File Placement

Use project style after inspecting neighboring modules. Suggested placement:

- `backend/rp/models/memory/runtime_memory_contract.py`
- `backend/rp/services/memory/runtime_memory_contract_registry.py`
- `backend/rp/models/memory/maintenance_candidate.py`
- `backend/rp/services/memory/memory_candidate_validation_service.py`

If implementation chooses different names, preserve responsibility separation:
registry models, registry service, candidate DTOs, and validator should not be
collapsed into one large file.

## Tests To Add Or Update

Add focused tests, likely:

- `backend/rp/tests/services/memory/test_runtime_memory_contract_registry.py`
- `backend/rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py`
- `backend/rp/tests/services/memory/test_memory_candidate_validation_service.py`

Minimum assertions:

- runtime longform registry exports exactly the five S3 domains in stable order;
- each domain exposes the exact required blocks;
- every block has primary `facts` field semantics, optionally groupable;
- unknown domain/block lookup fails closed;
- create/delete domain, create/delete block, and schema-change operation kinds
  are rejected;
- missing source refs are rejected;
- missing `base_block_revision_id` is rejected;
- unsupported operation is rejected;
- contradictory operations on the same target fact are rejected;
- valid append/update/remove candidates pass validation but do not mutate truth.

Regression:

- existing `backend/rp/tests/services/memory/test_memory_contract_registry.py`
  must still pass unless the implementer records a documented, reviewed reason.

## Gate Commands

Run at minimum from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/memory/test_memory_contract_registry.py
python -m pytest rp/tests/services/memory/test_runtime_memory_contract_registry.py
python -m pytest rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py
python -m pytest rp/tests/services/memory/test_memory_candidate_validation_service.py
```

If a test path is adjusted, run the equivalent exact test file(s) and state the
adjustment.

## Forbidden In S3a

- Do not import or reuse setup-agent code.
- Do not add memory-specific policy into harness core.
- Do not route candidates into proposal/apply yet.
- Do not implement model/tool execution yet.
- Do not commit from the implement worker.
- Do not touch unrelated visible worktree changes.

## Expected Implementer Output

Summarize:

- files changed;
- exact tests run and results;
- any deviations from this brief;
- remaining risks for S3b/S3c.
