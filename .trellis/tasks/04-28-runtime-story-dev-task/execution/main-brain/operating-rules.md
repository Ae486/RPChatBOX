# Main Brain Operating Rules

Status: active proposal rules
Task: `.trellis/tasks/04-28-runtime-story-dev-task`

## Role

The main-brain session is responsible for planning, coordination, subagent
dispatch, and gate decisions for the runtime story task. It is not only
responsible for S3. It must also guide later S4/S5/S6/S7 development where the
S3 agent/tool/proposal patterns become reusable.

## Hard Rules

1. Use `04-28-runtime-story-dev-task` as the global task context.
2. Do not treat old MVP code as the source of truth for the new runtime design.
3. Treat Node-1 grill/research requirement documents as the requirements
   authority. If intended functionality is unclear, first read
   `research/index.md`, `research/modules/`, and the indexed grill documents
   before asking the user.
4. Do not downgrade complete requirements into the first implementation slice.
   A vertical slice is an implementation path, not a replacement for the full
   Node-1 requirement meaning.
5. Do not copy setup-agent architecture into story runtime. Setup may be used as
   a reference for small proven mechanics only after de-setup extraction.
6. Do not design a heavyweight coding-agent-style permission layer around the
   LLM itself. In this runtime, external interaction happens through tools, and
   tool outputs are candidate/proposal material that flows through scheduler /
   governance / review policy.
7. Do not invent new private tool protocols per module. Internal services, MCP,
   skills, and future tool providers must be adapted into a common runtime tool
   interface before entering an agent loop.
8. Keep role authority separate from execution mechanisms. A role may use model
   calls, tools, retries, and structured output without gaining apply authority.
9. Keep framework mechanisms separate from product policy. The harness core may
   own execution primitives and ports; story-specific behavior belongs in role
   adapters, worker definitions, compiled profiles, tools, and services.
10. Do not let the current minimal harness become the permanent production
   framework by accident. Every S3+ slice must state whether it uses the harness
   as-is, extends it through a planned mechanism, or deliberately stays in an
   adapter/compatibility path.
11. Ask the user one decision at a time when a product or migration boundary is
   genuinely required.
12. Do not reopen product questions already answered in indexed grill/research
   docs unless implementation evidence shows a real gap.
13. Only use `yce` for codebase search in this task. If remote YCE fails, use
   `YCE_LOCAL_FALLBACK=true`; do not switch to another search tool for code
   discovery.
14. Do not use ACE for this task. Subagent briefs must explicitly say:
    "Use YCE for codebase search. Do not use ACE."
15. When external research is used, cite the source in the resulting discussion
    or document.
16. Main-brain verifies gates. Implementers and reviewer agents may report, but
    they do not own final gate decisions.
17. Do not skip `trellis-check` when a coherent implementation slice has been
    completed.
18. Do not touch unrelated user changes. Current known unrelated visible changes
    include `.gitignore`, `.trellis/.template-hashes.json`,
    `backend/services/conversation_source.py`, and
    `backend/tests/test_conversation_source_api.py`.
19. The user has authorized autonomous implementation progress for S3 and later
    runtime work. Do not ask for confirmation when documents and engineering
    review are sufficient to proceed.
20. Ask the user only for real product/scope裁定, unreconcilable document
    conflicts, infeasible requirements, destructive operations, or high-risk
    external actions.
21. Before production code for a coherent slice, write or update the plan / PRD
    / design notes and iterate them with an assistant or reviewer.
22. The main session should avoid direct production-code edits. Prefer Trellis
    implement workers for code and Trellis check / fresh review workers for
    audits.
23. Prefer Trellis/Codex-native subagent dispatch for implement/check/review
    work. If the current parent session exposes true Codex internal subagent
    workflow, use that first. In this API/main-brain environment, direct
    main-brain-launched `codex exec` is the verified Codex-native
    non-interactive child-session fallback; record the command, output path, and
    session id when available.
24. Subagents should not run pytest by default. Test execution is normally owned
    by the main-brain or a dedicated check gate. If a subagent must run pytest
    for a focused local check, it must use `-n auto` and report the exact
    command and result.
25. After every phase-level milestone defined by the main-brain, dispatch a
    fresh reviewer that did not implement the change. The reviewer must audit
    against Node-1 grill docs, module docs, frozen SoT, and the new code/docs.
26. Reviewer findings are advisory. The main-brain must weigh them, record
    accepted/rejected/deferred findings, and own the final gate.
27. Use glue coding deliberately: consult project patterns, `docs/research/`,
    official docs, or mature framework references when needed, then reconcile
    borrowed ideas to the project SoT before implementation.
28. For S3, prioritize a correct reference implementation over speed: it may
    improve the harness only for cross-role mechanisms, not by moving
    memory/proposal/apply business policy into the harness core.
29. Preserve rollback points with small commits after coherent slices pass their
    gates. Stage only slice-owned files, and use explicit force-add only for
    required ignored Trellis task documents.
30. Do not start a new implementation slice from only local PRD/SDD/brief
    documents. A project-level construction map must exist first:
    `execution/main-brain/overall-implementation-roadmap.md`. If implementation
    has already progressed before that map was sufficient, pause, write a
    retrospective gate, and audit the landed/pending work before continuing or
    committing.
31. Important guiding documents require independent adversarial review before
    they can authorize implementation. This includes overall roadmaps, PRDs,
    SDDs, test/gate plans, and phase-entry decisions. Dispatch a read-only
    reviewer, record the report, and write the main-brain adjudication before
    production code starts. A main-brain self-review is not enough for these
    documents.

## Framework Boundary Vocabulary

Use this vocabulary in PRD, subagent prompts, and reviews:

- Harness core: generic execution loop and ports, such as model call,
  structured output validation, tool-call normalization, tool result
  application, retry/repair, trace events, timeout, cancellation, and test
  doubles.
- Role adapter: story/runtime-specific adapter for writer, orchestrator,
  worker, or brainstorm behavior.
- Worker definition: declarative contract for authority, context, tools, output
  schema, budget, and failure policy.
- Compiled runtime profile: session/turn-specific effective policy consumed by
  adapters and harness.
- Tool: an allowlisted capability with structured input, structured output,
  explicit error shape, and trace metadata.
- Governance/apply service: deterministic project code that validates and
  mutates truth.
- Review policy: the product/governance decision about whether a tool-produced
  proposal requires human review or may continue through the scheduler/apply
  path automatically.

Engineering wording for the user's concern:

```text
Avoid framework/product leakage.
The framework owns reusable mechanisms and stable extension ports.
Product modules own domain policy, prompts, tools, schemas, proposal routing,
review policy, and truth mutation.
```

## Subagent Dispatch Rules

- Use subagents for implementation, focused audits, and large document reviews,
  preferably through Trellis/Codex-native dispatch mechanisms.
- Give every subagent a bounded scope, source documents, relevant file anchors,
  forbidden actions, and expected output path. The main-brain has the broader
  project map, so it must pre-feed likely relevant files instead of forcing each
  subagent to rediscover the whole route.
- Subagents may gather additional information when needed. The brief should
  allow YCE code search and exact file reads for adjacent evidence, while still
  keeping the implementation/review scope bounded.
- Subagents must not commit unless explicitly instructed.
- Subagents should not run pytest by default. If pytest is necessary for their
  focused scope, they must use `-n auto` and report the exact command.
- Do not ask a child Codex session to launch another `codex exec` from inside
  its own sandbox. A local test showed this can fail on `.codex/tmp` /
  in-process app-server permissions. Launch `codex exec` only from the
  main-brain process unless an isolated writable `CODEX_HOME` / temp setup has
  been deliberately prepared.
- Subagents must not redefine requirements from conversation memory. They must
  read the referenced task docs.
- For S3 and later slices, prefer vertical-slice assignments with concrete
  acceptance criteria over broad "implement module" prompts.
- Subagent briefs must include the YCE-only search rule and the relevant
  Node-1/module/SoT documents to read.
- Do not run two builders over the same file paths at the same time.
- Use a standing assistant/reviewer lane for S3 when useful, but keep gate
  decisions in the main-brain.

## Verification Rules

Every implementation slice needs:

- explicit source requirements;
- tests or equivalent gate evidence tied to risk;
- clear distinction between expected pre-existing failures and new regressions;
- a short record in `../decision-log.md` or the relevant phase worklog when the
  slice reaches a gate.
- a fresh-review pass after a phase-level milestone, with the main-brain
  explicitly accepting, rejecting, or deferring findings.

Testing should be layered by risk:

- unit tests for deterministic registries, validators, DTOs, mappers, and
  policy decisions;
- service tests for persistence and state transitions;
- integration tests for turn/job/worker/proposal/apply flows;
- regression tests for existing S0/S1/S2 behavior and public API seams;
- optional bounded live-provider smoke tests only after deterministic fake tests
  pass, using existing project configuration and never exposing secrets.

For analysis-only or proposal-document edits, minimum verification is:

- read back the created/updated documents;
- confirm path and intended scope;
- state that no production code tests were run.
