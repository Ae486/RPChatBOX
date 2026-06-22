# Harness Gap And Completion Plan

Status: active proposal control document
Task: `.trellis/tasks/04-28-runtime-story-dev-task`
Created: 2026-06-23

This document prevents the current minimal harness substrate from becoming the
permanent production framework by accident.

## Current Harness Reality

Current implementation provides a useful S0 substrate:

- setup-free generic tool call/result contracts;
- generic runtime graph shape;
- story-owned test harness with fake model and fake no-op tool;
- import audit proving the story harness path does not pull setup-agent modules.

This is a foundation, not the full target framework.

Production story turns still use:

```text
StoryGraphRunner
  -> StoryTurnDomainService
  -> legacy longform services / bootstrap worker adapters
```

The shared story harness is not yet the universal production executor for
writer, orchestrator, worker, and brainstorm roles.

## Target Harness Capability

The desired runtime-agent framework must provide these generic mechanisms:

| Capability | Belongs In Harness Core? | Notes |
| --- | --- | --- |
| model call gateway port | yes | Core owns the port, role adapter owns prompts and model policy. |
| structured output validation | yes | Core can run validators; role/worker owns schema. |
| normalized tool call/result loop | yes | Core owns loop mechanics; tools own domain behavior. |
| bounded retry/repair | yes | Core owns limits and loop control; adapter owns repair prompt/schema. |
| timeout/cancellation | yes | Core owns runtime mechanics and trace. |
| trace/event sink | yes | Core emits stable execution events; visibility policy is role/profile-owned. |
| fake model/fake tool testing | yes | Required for reliable vertical-slice tests. |
| context packet policy | no, adapter/profile | Harness receives curated context; product code decides what is visible. |
| memory/domain/block semantics | no, product services/tools | Must not be embedded into framework core. |
| proposal/apply governance | no, deterministic services | Harness may call tools/services, but proposal routing, review policy, and apply are outside the generic loop. |
| writer prose policy | no, writer adapter | Not generic framework behavior. |
| brainstorm product loop | no, brainstorm adapter | Not generic framework behavior. |

## Gap List

### Required Before S3 First Vertical Slice

- A common runtime tool interface for internal project tools:
  structured input, structured output, explicit error shape, trace metadata,
  allowlist, and unknown-tool behavior.
- Role/worker definition shape for the first S3 worker:
  context policy, tool allowlist, output schema, loop limits, failure policy,
  and proposal review routing.
- Governance routing policy:
  review-required, direct-apply-allowed, and blocked/invalid fail-closed paths
  must be represented before the first S3 slice is considered complete.
- Structured candidate output validation:
  schema-bound candidate material, no free-form truth mutation.
- Harness/adapter boundary:
  the first S3 worker must not hardcode story memory policy inside generic
  harness core.
- Test doubles:
  fake model and fake tool paths that can prove tool calls, schema invalid,
  permission denied, stale base, and success cases.
- A written S3 slice design reviewed by an assistant/reviewer before production
  code. The design must state which harness gaps are closed now, which remain
  bounded, and which are deferred with an owner.
- A fresh-review gate after the S3 milestone to ensure the landed code still
  matches Node-1 grill docs, module docs, frozen SoT, and this harness boundary
  plan.

### Allowed During S3 If Explicitly Bounded

- Full universal production executor unification across writer/orchestrator/
  worker/brainstorm may remain incomplete if the first S3 slice clearly states
  which adapter path it uses.
- Advanced multi-tool or MCP providers may be deferred; first slice can use
  internal project tools only.
- Full prompt/repair sophistication may be limited if the structured output
  contract and failure behavior are enforced deterministically.

### Deferred Until After S3 Unless Needed

- External MCP/skill provider support.
- Multi-agent handoff or agent-as-tool patterns.
- Generic UI event streaming for every role.
- Complete replacement of every legacy longform service.
- Full brainstorm agent family replacement.

## Completion Gates

Before a slice claims "harness-complete enough", it must answer:

1. Which part is generic harness core?
2. Which part is role adapter or worker definition?
3. Which tools are exposed, and through what structured contract?
4. What tool-produced proposal path does the role use?
5. What happens on unknown tool, invalid schema, timeout, stale base, permission
   denied, and partial tool failure?
6. What trace/debug evidence proves the run?
7. Which old MVP path, if any, is still being used as compatibility/adaptation?
8. Which tests prove deterministic behavior without a live provider?
9. Was a fresh reviewer dispatched after the milestone, and how did the
   main-brain adjudicate the findings?

Optional live-provider tests, including DeepSeek-backed smoke tests through
existing project configuration, may support the gate only after deterministic
fake tests pass. They must not print or expose secrets and must not substitute
for deterministic unit/service/integration coverage.

## Anti-Patterns To Reject

- Adding memory-specific logic directly into the harness core.
- Building a coding-agent-style permission layer for the LLM when all external
  action already goes through tools and proposals.
- Treating tool names alone as enough review/governance policy.
- Creating a new tool protocol for each module.
- Letting writer output imply proposal/apply authority.
- Hiding failed tool/schema cases inside assistant prose.
- Calling legacy longform services "the agent framework" because they happen to
  sit behind a graph node.
- Proceeding with S3 because "the fake harness works" without a gap list.

## Engineering Framing

The concern is valid and should be described as:

```text
framework/product leakage and policy coupling risk.
```

Good engineering framing:

```text
The framework should own reusable execution mechanisms and stable ports.
Product-specific policy must live in adapters, definitions, profiles, tools,
proposal routing/review policy, and deterministic services.
```

This is a normal separation-of-concerns / ports-and-adapters issue, not a vague
style concern.

## S3-To-Harness Rule

S3 should be used to prove the harness, not to expand the harness with S3
business policy.

Promote to harness only when the code is true cross-role execution mechanism:

- model call / stream normalization;
- structured output validation;
- normalized tool loop;
- bounded repair/retry;
- timeout/cancellation;
- trace/event sink;
- test doubles and failure injection;
- extension ports.

Keep in role adapters, worker definitions, tools, profiles, or services when
the code is product-specific:

- memory block/domain semantics;
- fact/projection candidate shape;
- proposal review policy;
- apply semantics;
- packet content choices;
- writer/brainstorm/persona behavior.
