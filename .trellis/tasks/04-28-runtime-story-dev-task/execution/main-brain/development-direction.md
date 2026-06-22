# Development Direction

Status: active proposal direction
Task: `.trellis/tasks/04-28-runtime-story-dev-task`

## Current Position

The current MVP story runtime is not a plain chat flow. It has a graph-shaped
production shell and a setup-free S0 harness substrate.

However, it is not yet the full story-agent framework described by the current
runtime design. Production turns still run through `StoryGraphRunner`,
`StoryTurnDomainService`, and legacy longform services. The shared
`story_harness` is currently a substrate and test proof, not the universal
production executor for all story roles.

## Requirement Authority

Node-1 grill/research documents are the requirements authority. Implementation
planning must translate those requirements into code; it must not re-invent
requirements from partial current code or from conversation memory.

When a requirement question appears, the order is:

```text
research/index.md
  -> research/modules/
  -> indexed grill/source documents
  -> execution frozen SoT / slice docs
  -> user only if the documents do not answer it or conflict
```

This is especially important for S3 and later modules. The first business
closure is only a vertical implementation slice. It must not narrow the complete
meaning of memory workers, scheduler, tools, proposal review, or story-agent
framework.

## D1 Direction: Old MVP Chain Handling

The old MVP chain must be split by responsibility:

| Area | Direction |
| --- | --- |
| Agent execution shape | Replace or reconnect to the new story-agent harness. This includes writer, orchestrator, worker execution loops, and the pseudo-brainstorm surface when it becomes a real runtime agent. |
| Memory truth / domain / block / proposal / apply | Follow the latest S3 design. Legacy memory patches or specialist bundles must not define new runtime truth. |
| Runtime control plane | Preserve or adapt when compatible. This includes branch control, checkpoint binding, turn identity, runtime profile snapshot, and debug read surfaces. |
| Draft / review / rewrite mechanics | Preserve or adapt if compatible with the new packet/sidecar/adoption contracts. |
| Legacy longform command surface | Keep only as compatibility surface / adapter while migrating. |
| Reusable old mechanics | Extract only if they can be made setup-free, legacy-free, and contract-owned by the new runtime. |

Short form:

```text
Old MVP code may support compatibility, state, and migration.
Old MVP agent/memory semantics must not continue as the new runtime authority.
```

## Harness Direction

The target architecture remains:

```text
project-owned runtime harness
  -> role / worker definitions
  -> compiled runtime profile
  -> common tool interface
  -> deterministic scheduler / governance / apply boundaries
```

The harness should provide model calls, structured output validation,
allowlisted tool loops, bounded retry/repair, tracing, timeout/cancellation, and
test doubles. Role adapters and worker definitions decide authority, tool
allowlist, output schema, context policy, event visibility, and failure
behavior.

## D2 Direction: Minimum Base Before S3

S3 should use S0/S1/S2 as the minimum production gate:

```text
S0: setup-free harness substrate exists
S1: turn identity / settlement / interrupt basics are reliable
S2: scheduler / job / worker execution has a trustworthy minimum path
```

This does not mean waiting for a perfect universal story-agent framework. It
does mean the main-brain must not let S3 run permanently on the current minimal
test substrate as if that were the desired framework.

Before S3 implementation planning is treated as ready, the main-brain must keep
an explicit harness gap list and decide which gaps are:

- required before the first S3 vertical slice;
- allowed during the first S3 vertical slice if bounded and documented;
- deferred until after S3 with an owner and reason.

The key guardrail:

```text
Do not confuse "minimum base gate" with "complete enough forever".
```

## S3 Direction

S3 should be the first real proof that the new agent/tool/proposal style works.
It should not begin as a full memory-system rewrite.

The likely first vertical slice is:

```text
accepted source material
  -> post-write trigger
  -> optional orchestrator dispatch proposal
  -> scheduler-selected memory worker
  -> tool-produced structured candidate/proposal
  -> scheduler/governance/review policy
  -> apply/debug/next-packet visibility
  -> tests for invalid schema, stale base, review-required, and success
```

This slice should establish reusable patterns for:

- runtime tool input/output/error shapes;
- structured LLM output handling;
- source refs and base revisions;
- proposal/apply separation;
- deterministic truth mutation;
- proposal review policy: when tool-produced proposals require human review
  versus when they may continue through scheduler/governance automatically;
- minimal complete governance routing for the first slice: review-required,
  direct-apply-allowed, and blocked/invalid fail-closed outcomes;
- trace/debug/read-manifest evidence;
- legacy adapter downgrade rules.

This first slice is not the full S3 requirement. It is the first route through
the complete design. Any deferred S3 capability must be named as deferred, not
silently removed.

## S3 Implementation Leadership

The user has authorized implementation to continue without further confirmation
when the main-brain and assistant/reviewer can determine the direction from
documents and code evidence.

Before S3 code, the main-brain should produce or update a slice design / PRD
covering:

- source documents read, especially Node-1 grill docs and `research/modules/*`;
- exact first vertical-slice scope and explicit deferred S3 capabilities;
- harness-core versus worker-adapter versus memory/proposal/apply service
  boundaries;
- internal runtime tools and their structured input/output/error contracts;
- review-required, direct-apply-allowed, and blocked/invalid governance
  routing;
- state records and migration/adapter points;
- unit, service, integration, regression, and optional live-provider smoke
  tests;
- fresh-review plan after the milestone.

The main-brain should iterate the plan with an assistant/reviewer, then dispatch
implementation through Trellis implement workers. The main session should
normally avoid production-code edits and instead own direction, review,
verification, and gate decisions.

S3 implementation must keep these boundaries visible:

| Area | Direction |
| --- | --- |
| Harness improvements | Allowed only for cross-role execution mechanisms such as structured output validation, normalized tool loop, trace, timeout/cancellation, retry/repair, and fakes. |
| Memory/domain/block | Product service / memory module responsibility, not harness core. |
| Proposal/review/apply | Deterministic governance/apply services, not LLM authority and not generic harness policy. |
| Tools | Common runtime tool interface with structured input/output/error and trace; no private per-module protocols. |
| Old MVP paths | Adapter evidence only; preserve compatible control-plane mechanics, but do not let legacy semantics define S3 truth. |

After each phase-level milestone, dispatch a fresh reviewer that did not
implement the slice. The reviewer audits the landed work against Node-1 docs,
module docs, frozen SoT, and the slice plan. The main-brain weighs the findings
and records the gate decision.

## Later Development Direction

S4/S5/S6/S7 should reuse the patterns proven by S3 rather than inventing
separate loops:

- S4 retrieval should be a service/tool capability, not an agent family.
- S5 chapter summary should use the same source-ref/proposal/trace discipline
  where it mutates memory or durable state.
- S6 draft review/rewrite should preserve no-auto-adoption and explicit
  adoption semantics, while using packet/sidecar boundaries.
- S7 brainstorm should become harness-compatible only when it needs real
  agent behavior; the lightweight product loop may remain a compatibility
  surface until then.
