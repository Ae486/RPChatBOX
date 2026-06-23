# Implementation Leadership Rules

Status: active mandatory control rules
Task: `.trellis/tasks/04-28-runtime-story-dev-task`
Created: 2026-06-23

This file records how the main-brain session must lead S3 and later runtime
implementation. It is a control document for planning, delegation, review, and
verification. It does not replace frozen requirements in `research/` or
`execution/phase-*`.

## User Authorization

The user has authorized autonomous implementation progress for S3 and later
runtime work.

The main-brain does not need to ask the user before proceeding when:

- the requirement is already answered by Node-1 grill docs, module docs, frozen
  SoT, or execution slice docs;
- the question is an engineering implementation choice such as DTO names,
  storage placement, test structure, or adapter layout;
- the main-brain and assistant/reviewer have reviewed the issue and can
  determine the direction from evidence.

The main-brain must ask the user only when:

- documents conflict and cannot be reconciled by authority order;
- a choice changes product behavior, delivery scope, or user-visible workflow;
- implementation evidence proves that an existing requirement is infeasible
  without changing the requirement;
- a destructive operation or high-risk external action is required.

## Authority Order

Use this order before asking the user:

```text
research/index.md
  -> research/modules/
  -> indexed Node-1 grill/source documents
  -> execution/phase-1-spec-freeze/
  -> execution/phase-3-slicing/
  -> execution/decision-log.md
  -> execution/main-brain/
  -> current code evidence
  -> user only if the above cannot answer it
```

The Node-1 grill documents are requirement authority. The module documents are
the secondary implementation-reading layer. Later execution documents are
process and gate evidence. If a document had no expected future value, it should
not have been written; therefore implementation planning must actively reuse
the documents instead of relying on memory or partial current code.

## Main-Brain Operating Model

The main-brain is the highest-authority execution leader for this task.

Responsibilities:

- maintain the development direction;
- define coherent implementation slices;
- write or require plan / PRD / design notes before code;
- coordinate implementation agents and reviewer agents;
- resolve engineering choices that do not require user裁定;
- own final verification and gate decisions;
- record decisions, gates, and review outcomes.

The main-brain should avoid direct production-code edits. Direct edits are
allowed only for small control/document updates, emergency tiny fixes, or when
no safe delegation path exists. Production implementation should normally be
delegated.

## Standing Assistant And Review Loop

Maintain a standing assistant/reviewer lane for S3. In current Trellis terms,
this means using delegated implement/check/review workers through Trellis or
Codex-native subagent dispatch rather than turning the main session into the
only engineer. Avoid ad-hoc raw CLI/session dispatch unless the native path is
unavailable, and record the reason when an exception is used.

Current Codex dispatch finding, verified 2026-06-23:

- official Codex docs describe true internal subagent workflows, but the current
  non-interactive `codex exec` environment used from this API session does not
  expose a built-in spawn tool to the child session;
- direct main-brain-launched `codex exec` does work as an official
  non-interactive child-session dispatch path;
- do not nest `codex exec` inside a child Codex sandbox as the default
  mechanism, because local testing hit `.codex/tmp` / in-process app-server
  permission failures.

Recommended loop:

```text
main-brain reads docs and drafts slice plan
  -> assistant/reviewer critiques plan against docs/code
  -> main-brain weighs feedback and freezes slice brief
  -> implement worker lands code/tests without committing unless instructed
  -> main-brain runs or verifies gates
  -> fresh reviewer audits the landed slice against Node-1/module/SoT docs
  -> main-brain accepts/rejects reviewer findings
  -> record decision/worklog/gate
```

Reviewer output is advisory, not binding. The main-brain must weigh findings
against documents, code evidence, test results, and project direction. Do not
blindly accept a reviewer, and do not blindly defend current work.

## Fresh Reviewer Rule

After each phase-level milestone, the main-brain must dispatch a fresh reviewer
that did not implement the change.

The main-brain defines the milestone size. Examples:

- S3 design/oracle plan finalized;
- S3 first vertical-slice code landed;
- governance routing path landed;
- memory registry/candidate/apply path landed;
- a coherent test/gate suite passes;
- harness extension promoted from S3 into shared core.

Fresh reviewer scope:

- read `research/index.md` and relevant `research/modules/*`;
- read frozen SoT and slice plan entries;
- inspect the new code/docs;
- identify requirement drift, framework/product leakage, missing tests, unsafe
  coupling, old-MVP leakage, and false-green tests;
- report blockers, concerns, and non-blocking notes separately.

The main-brain then records which findings are accepted, rejected, or deferred,
with reasons.

## Planning Before Code

Before production code for a coherent slice, create or update a slice design
that states:

- source requirement documents;
- exact scope and out-of-scope items;
- old code paths to preserve, adapt, or replace;
- harness/core versus role adapter versus product service boundaries;
- tool contracts and structured input/output/error shapes;
- proposal/review/apply routing;
- data/state records touched;
- failure modes;
- tests and gate commands;
- expected pre-existing failures, if any.

The plan should be iterated with a reviewer/assistant before implementation.
If the plan conflicts with Node-1/module/SoT docs, fix the plan before code.

## Glue Coding Rule

Use glue coding deliberately:

- study existing project patterns first;
- consult `docs/research/` and relevant reference repos when a pattern is not
  obvious;
- search official docs or mature framework examples when designing tools,
  structured output, retries, errors, or agent loops;
- cite external sources in documents or discussion when external research is
  used;
- reconcile every borrowed idea to project SoT before implementing it.

Borrow ideas and patterns. Do not copy setup-agent architecture, old MVP
semantics, or external framework authority into story runtime.

## Search And Tooling Rule

For codebase search in this task, use YCE only. Do not use ACE.

Subagent briefs must include:

```text
Use YCE for codebase search. Do not use ACE. If YCE remote search fails, set
YCE_LOCAL_FALLBACK=true and retry. Exact known file reads are allowed after
paths are known.
```

Direct reads of known indexed docs are preferred over semantic search when the
path is already known.

Subagent testing rule:

- subagents should not run pytest by default;
- the main-brain or a dedicated check gate normally owns pytest execution;
- if a subagent must run pytest for a narrow local check, it must use `-n auto`
  and report the exact command and result;
- do not let implement workers spend time on broad test sweeps unless the slice
  brief explicitly assigns that responsibility.

## S3 Leadership Rules

S3 is the current priority and the reference implementation for later story
agent work.

S3 must prove:

- common runtime tool interface for internal project tools;
- structured output validation;
- memory worker candidate material that is not truth;
- governed apply as the only truth mutation path;
- review-required, direct-apply-allowed, and blocked/invalid governance routing;
- stale base rejection without model self-repair;
- readable trace/debug evidence;
- test doubles for fake model/tool paths;
- clear harness versus product-service boundaries.

S3 may improve the harness when the improvement is a true cross-role mechanism.
Keep memory/domain/block semantics, proposal review policy, Core/projection
apply rules, and packet content policy outside the harness core.

## Testing Strategy

Testing must prove behavior, not only implementation shape.

Use a layered gate:

| Layer | Purpose | S3 examples |
| --- | --- | --- |
| Unit tests | Validate deterministic validators, mappers, registries, DTOs, policy decisions. | domain registry exact five-domain set; candidate schema rejects create-block; policy maps review/direct/blocked. |
| Service tests | Validate state transitions with real services and DB/session fixtures. | worker candidate material stays non-truth; stale base reject; apply writes receipts. |
| Integration tests | Validate end-to-end runtime flow across turn/job/worker/proposal/apply. | accepted segment -> scheduler gate -> memory worker -> proposal/direct apply -> lock release. |
| Regression tests | Protect existing S0/S1/S2 behavior. | turn settlement, interruption, scheduler idempotency, existing rp_story API. |
| Review/audit tests | Catch false-green and requirement drift. | fresh reviewer checks new code against Node-1/module/SoT docs after each milestone. |
| Optional live-provider smoke | Validate real LLM/tool behavior when deterministic fakes pass. | bounded DeepSeek-backed worker run with no secret logging, using existing project config only. |

Default rule:

- deterministic fake tests are required for CI-quality confidence;
- live-provider tests are optional supporting evidence and must be bounded,
  repeatable enough for smoke use, and must not expose keys;
- failing or flaky live-provider tests do not replace deterministic failures;
- every external API/key use must follow existing project configuration and
  never print secrets.
- broad pytest gates should be run by the main-brain or a dedicated check
  worker; if a subagent runs pytest, use `-n auto`.

## Review Quality Bar

A slice is not accepted just because tests pass.

Before gate pass, the main-brain must check:

- requirements source coverage;
- code boundaries and file organization;
- no setup-agent or old-MVP semantic leakage;
- no framework/product leakage;
- structured errors and readable debug evidence;
- negative cases, not only happy path;
- no unrelated user changes touched;
- no weakened tests or curve-fit assertions;
- trellis-check outcome for coherent implementation slices.

## Versioning And Commit Discipline

Use commit history as the rollback boundary for S3 and later runtime work.

Rules:

- make one small, readable commit after each coherent planning, implementation,
  or verification slice passes its gate;
- do not commit partial code that has not reached its stated slice gate, unless
  the commit is explicitly marked as documentation/planning only;
- stage only explicit paths owned by the slice;
- never stage unrelated user changes;
- because `.trellis/tasks/` is ignored in this worktree, use explicit force-add
  only for task documents that must be preserved for coordination or rollback;
- prefer fix-forward inside the same small slice while the diff is tiny; if a
  landed slice is wrong, revert that slice commit instead of broad worktree
  resets;
- record commit hashes for meaningful milestones in the S3 worklog or gate
  record.

## Documentation And Records

Use:

- `execution/decision-log.md` for ADR/gate-level decisions;
- the relevant `execution/phase-*` worklog/gate for slice progress;
- `execution/main-brain/*` for active leadership rules and direction;
- `research/modules/*` only when a control-rule becomes a stable module
  requirement and should be promoted.

Keep records clear enough that a future agent or human can continue without
reading raw conversation logs.
