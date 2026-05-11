# SetupAgent Architecture Spine Spec

> Task-local architecture spec for setup-stage-tool-call-recursion-bugfix.
>
> This is a planning/spec document. It proposes the target spine and implementation contracts for later subagent work.

## 1. Scope / Trigger

Trigger this spec when changing SetupAgent runtime loop, setup graph shell, model request/response handling, tool execution, repair policy, stage tool scope, setup typed SSE mapping, or setup visible transcript behavior.

This spec does not authorize changes to runtime-story Q files or runtime-story implementation.

## 2. Product Interpretation

The product is not a normal chat app where the model only emits text. It is a creative-agent CLI/workbench:

- Claude Code manages code by reading, editing, running tools, repairing failures, and preserving session context.
- This project manages creative setup/runtime state: world background, characters, outline, draft entries, memory/retrieval chunks, review, commit, readiness, and later active story runtime.
- SetupAgent is the first controlled agent loop. It must become reliable enough to serve as reference infrastructure for later runtime agents.

## 3. Source Lessons

### 3.1 pi-mono

Useful pattern:

```text
AgentSession
  -> Agent state/events
  -> agent_loop
  -> model stream
  -> tool execution
  -> toolResult message
  -> continue / stop
```

Borrow:

- stateful wrapper separate from loop
- event stream as first-class output
- `convert_to_llm` / `transform_context` as ports
- steering/follow-up queues as explicit session controls
- retry/compaction handled at session boundary instead of inside every tool

Do not borrow blindly:

- coding tool names or file-edit semantics
- generic session persistence as setup business truth
- minimal loop as sufficient production behavior

### 3.2 Claude Code docs

Borrow:

- session/query split
- recoverable error withholding and repair before user-visible failure
- tool lifecycle: lookup, schema validation, permission/scope, execution, result mapping
- context engineering pipeline before every model call
- skill packs as prompt templates, not business contract owners
- typed tool UI rendering distinct from assistant text
- bounded continue sites with explicit reason labels

Do not borrow blindly:

- code-file-specific assumptions
- shell permission model as-is
- massive tool inventory
- coding-agent UI decisions that do not map to creative drafting

### 3.3 claude-code-from-scratch

Borrow:

- simplest readable loop as implementation sanity reference
- OpenAI-compatible backend handling as a concrete example
- basic tool registry, deferred tools, session persistence, and cost/turn budget concepts
- read/execute/write separation as analogy for creative read/write/edit operations

Do not borrow blindly:

- single large `Agent` class as final structure
- string-only tool result model
- simple JSON session as sufficient project persistence

## 4. Signatures / Ports

The target code may keep existing class names where cheaper, but it must expose these responsibilities clearly.

### 4.1 `SetupAgentSession`

Responsibilities:

- bind workspace/session/user turn
- select model and capability profile
- load and persist visible dialogue when dialogue persistence is implemented
- own cancellation and stream lifecycle
- call `SetupTurnLoop`
- map final turn result to API/SSE response

Must not:

- mutate draft internals directly
- decide stage draft schema
- render pseudo tool code as text

### 4.2 `SetupTurnLoop`

Responsibilities:

- run one user turn through model/tool iterations
- track bounded turn count and no-progress count
- carry current action expectation / obligation
- hand tool results to decision policy

Required loop states:

- `build_context`
- `call_model`
- `inspect_output`
- `execute_tools`
- `apply_observation`
- `decide_next`
- `finalize`

### 4.3 `SetupContextPipeline`

Responsibilities:

- assemble `SetupContextPacket`
- govern current-stage discussion history
- inject compact summary and draft refs
- inject stage overlay and SkillPack prompt
- inject runtime obligations and latest tool outcomes

Must preserve:

- current draft snapshot as truth context
- prior-stage accepted handoff context
- separation from Memory OS mutation

### 4.4 `ModelGateway`

Responsibilities:

- transform setup tools to provider-compatible schemas
- normalize OpenAI-compatible tool names when necessary
- strip unsupported thinking/tool-result features based on capability policy
- classify provider/gateway failures

### 4.5 `OutputInspector`

Responsibilities:

- identify real tool calls
- identify ordinary assistant text
- identify pseudo tool code leakage
- identify malformed tool-call arguments
- produce an inspect result for `DecisionPolicy`

Pseudo tool code examples must match patterns such as:

- `tool_code`
- `print(default_api.<tool>(...))`
- direct code text that clearly attempts a tool invocation instead of a natural response

### 4.6 `SetupToolRuntime`

Responsibilities:

- enforce turn tool scope
- validate arguments
- execute provider/local tools
- convert results into observations
- preserve typed tool events

Tool errors are data. A validation failure should return a machine-readable observation suitable for repair unless policy marks it unrecoverable.

For draft operations, the runtime should target one shared CRUD core rather than one bespoke tool family per stage. Stage-local differences belong in the exposure layer (SkillPack / stage prompt / tool scope), not in duplicated CRUD semantics.

### 4.7 `DecisionPolicy`

Responsibilities:

- decide `continue`, `repair`, `ask_user`, `finish`, or `fail`
- enforce retry budget
- detect repeated same failure/no-progress
- prevent graph recursion loops
- preserve distinction between turn finish and setup stage readiness

Required decisions:

| Input | Decision |
| --- | --- |
| real tool call success and no further obligation | finish or ask model for short visible summary, depending stream contract |
| recoverable tool validation failure | continue with repair obligation |
| same validation class repeats beyond budget | fail_retry_budget |
| pseudo tool text while tool required | continue repair if budget remains, otherwise fail_invalid_tool_output |
| pure text while no tool required | finish_text |
| pure text while action expectation requires write | repair or ask_user, not finish_text |

### 4.8 `SetupEventSink`

Responsibilities:

- emit typed SSE for assistant text, tool start, tool result, failure, and final state
- keep internal trace/debug/pseudo code out of visible assistant content
- preserve existing frontend tool-event display contract

## 5. Contracts

### 5.1 Loop Stop Contract

Every model/tool iteration must end with exactly one decision:

- `continue_reason`
- `finish_reason`
- `failure_reason`

`GRAPH_RECURSION_LIMIT` must never be the intended stop condition.

### 5.2 Repair Contract

Recoverable tool failures are withheld from final user-visible failure until repair budget is exhausted.

The next model call must receive:

- failed tool name
- validation/provider error message
- expected corrected shape or concise repair instruction
- remaining repair budget
- current action expectation

### 5.3 Tool Scope Contract

The model sees only tools allowed for the current setup stage/step. Execution also enforces the same allowlist.

Active direction:

- use one shared draft CRUD core for all stages
- expose the CRUD surface through stage-local SkillPack/prompt packaging
- retire legacy conflicting write paths after the new tool set passes tests

### 5.4 Draft Write Contract

The preferred direction is now a unified content-first deterministic draft CRUD core:

```text
LLM: entry_type, title, summary, content, tags, metadata hints, operation intent
Tool code: IDs, schema shape, type registry, merge/delete semantics, delta tracking, retrieval metadata
```

Model-facing stage differences should be carried by stage-local exposure and SkillPack guidance, not by duplicating CRUD semantics per stage.

### 5.5 SkillPack Contract

SkillPack is a stage-local prompt pack:

- helps the model think/design in a stage
- may include stage-specific drafting guidance
- helps decide which CRUD subset/overrides are surfaced for the stage
- does not mutate draft state
- must hard-unload when stage changes

### 5.6 Setup Lightweight Retrieval Contract

Setup retrieval is a setup-owned context capability during prestory editing. It is not the Memory OS retrieval broker and must not become a heavy RAG dependency for normal stage drafting.

The setup stage loop uses three read surfaces:

| Read surface | Owner | Purpose | Must not read |
| --- | --- | --- | --- |
| current-stage draft snapshot | `SetupContextPipeline` | provide the current editable stage truth in the model request | prior raw discussion as truth |
| `setup.read.draft_refs` | setup tool runtime | recover exact current-stage draft details referenced by compact summaries, working digests, or UI refs | Memory OS state or unrelated prior-stage raw discussion |
| `setup.truth_index.search/read_refs` | setup truth index | locate and exact-read accepted setup truth from committed snapshots | editable drafts from other stages or retrieval-core indexes |

The intended stage flow is:

```text
enter stage
  -> load prior accepted stage handoffs
  -> load current stage draft snapshot, SkillPack, working digest, compact summary
  -> discuss with user
  -> agent draft CRUD or user direct edit
  -> reconcile user edit deltas when needed
  -> read setup.read.draft_refs when compacted current-stage detail is needed
  -> search setup.truth_index when prior committed truth is only known semantically
  -> read setup.truth_index.read_refs before using exact committed details
  -> user explicitly commits
  -> persist accepted snapshot and commit handoff
  -> rebuild or make rebuildable setup truth index rows
  -> emit retrieval seed sections for retrieval-core materialization
  -> next stage receives compact accepted handoff, not raw prior discussion
```

Boundaries:

- Setup owns editable draft visibility, draft refs, stage handoff summaries, committed setup truth refs, lexical/path/filter truth-index search, and exact committed truth reads.
- Retrieval-core owns downstream chunk storage, embedding, hybrid search, reranking, retrieval cards, Recall/Archival search, and runtime retrieval policy.
- The bridge is materialization after commit: setup accepted entry/section trees produce retrieval seed sections; retrieval-core consumes those seeds but does not own editable setup draft truth.
- The agent never writes retrieval index rows or seed chunks directly. Fixed backend code derives those artifacts from accepted snapshots.
- `entry_type`, tags, aliases, summaries, semantic paths, and retrieval roles are draft/search metadata because they affect later recall quality. Their canonical source is the accepted setup draft tree, not hidden agent memory.

Claude Code analogy:

| Claude Code pattern | SetupAgent equivalent |
| --- | --- |
| project guide / memory file kept small and loaded intentionally | stage SkillPack, prior-stage handoff, compact summary |
| file index or grep finds candidates | `setup.truth_index.search` returns bounded refs and previews |
| read exact files only after locating them | `setup.truth_index.read_refs` and `setup.read.draft_refs` fetch bounded exact payloads |
| avoid stuffing the whole repo into context | avoid stuffing all drafts and prior dialogue into context |
| tool code owns file edits and validation | draft CRUD / truth-index / seed materialization code owns IDs, schema, refs, fingerprints, and persistence |

Implementation implications:

- The model should be prompted to search then read when it only remembers a proper noun or compact hint but lacks exact details.
- Search results must be small candidate lists, not full payload dumps.
- Exact reads must identify source kind: editable draft ref, committed setup truth ref, or retrieval seed/diagnostic ref when later implemented.
- No setup turn should call Memory OS retrieval merely to recover setup draft truth that is already available through setup refs.
- Existing typed SSE tool events remain user-visible for setup read/search tool calls, while internal selection traces stay out of assistant text.

## 6. Good / Base / Bad Cases

Good:

- user asks to add a world background entry
- model emits a real tool call
- tool writes deterministic draft entry
- typed tool events render
- loop stops with a concise visible response

Base:

- user asks a conceptual question
- no tool is required
- model emits normal text
- loop ends as `finish_text`

Bad:

- model prints `tool_code print(default_api...)`
- frontend shows that as assistant answer
- user says "call the tool"
- model calls a tool successfully
- graph keeps cycling until recursion limit

## 7. Tests Required

Implementation slices must add or update focused tests for:

- output inspector rejects pseudo tool text under tool-required expectation
- tool validation failure causes repair continuation before final failure
- successful `discussion.update_state` / draft write result routes to deterministic stop/next decision
- repeated same failure stops with retry-budget reason
- typed SSE tool events remain visible
- internal trace/pseudo tool code is not delivered as assistant text
- current stage tool scope snapshot matches active spec or explicit updated spec
- compacted current-stage detail is recovered through `setup.read.draft_refs`
- prior committed stage detail is located through `setup.truth_index.search` and exact-read through `setup.truth_index.read_refs`
- setup accepted snapshot emits retrieval seed material through fixed code without model-authored index/chunk payloads

## 8. Wrong vs Correct

### Wrong

- Treat LangGraph recursion limit as the loop safety mechanism.
- Make the prompt solely responsible for correct tool JSON.
- Expose many overlapping write tools and hope the model chooses correctly.
- Show internal pseudo tool code to the user as assistant text.
- Hide `setup.truth.write` in canonical stages without spec change.
- Treat setup draft recovery as Memory OS retrieval.
- Ask the model to author truth-index rows or retrieval seed chunks.

### Correct

- Keep LangGraph as a bounded execution substrate, with explicit policy stop reasons.
- Make runtime/tool code own known structure and validation.
- Expose a small stage-aware tool set.
- Convert tool errors into repair observations.
- Keep visible dialogue, typed tool events, and internal cognition separate.
- Update specs before changing the canonical draft write surface.
- Keep setup lightweight retrieval setup-owned during editing, then hand accepted seed material to retrieval-core after commit.
