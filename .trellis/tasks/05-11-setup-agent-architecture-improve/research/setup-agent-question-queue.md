# SetupAgent Architecture Question Queue

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Status: A0 question queue

## 1. Current Blocking Status

No blocking `$grill-me` question remains before completing A0 planning.

The user has confirmed the key口径:

- current code is product-semantics evidence, not architecture authority
- pi-mono is the minimal layering reference
- Claude Code is the mature module/function reference
- mature references may be adapted directly when the concern is not a setup-specific product requirement
- product-specific setup truth stays governed by current setup contracts
- tool calling remains standard prompt/schema/model tool-call/runtime execution flow
- different setup stages expose different tool/capability packages
- transition rules belong inside `SetupTurnLoop`, not a larger standalone policy god object

## 2. Confirmed Defaults

| Topic | Default answer | Source |
| --- | --- | --- |
| Current code quality | Use it to infer required behavior, not to preserve current boundaries | user clarification + HLD |
| Tool failure repair | Recoverable structured errors become observations and bounded retry before user-visible terminal failure | user example + current tool repair specs |
| Tool exposure | CapabilityPlan owns exposure; ToolProvider owns execution | grill decisions + Claude Code active tool filtering |
| Prompt guidance | Derived from capability package; not permission source | grill decisions |
| SkillPack governance | Prompt/context packaging only; stage-keyed activation and metadata-only observability | D governance closeout + active SkillPack spec |
| Output leakage | OutputInspector classifies before tool/runtime/transcript | HLD + Claude Code output separation |
| Event transcript | EventSink owns public/private visibility | HLD + typed SSE project contract |
| LangGraph | Keep as substrate, not architecture vocabulary | PRD + audit |

## 3. Future `$grill-me` Questions

Ask these only when implementation reaches the trigger.

### Q1. Should `SetupCapabilityPlan` become a concrete code object in A2?

Recommended default:

```text
Yes, but only after A1 proves the loop/output boundary. In A2, introduce a concrete plan object if it reduces prompt/schema/allowlist drift without moving business schemas or execution into the plan.
```

Source:

- Claude Code tool pools / active tool filtering
- pi-mono `AgentContext.tools`
- current drift across `profiles.py`, adapter, provider, prompt, and tests

Trigger:

- A2 implementation starts and the existing `profiles.py` + adapter structure cannot express snapshotable capability packages cleanly.

### Q2. What is the minimum A1 code slice?

Recommended default:

```text
Typed OutputInspector result + loop transition handling for pseudo tool text and recoverable tool error observations, with focused tests proving no visible pseudo text and no recursion-limit terminal.
```

Source:

- old 05-09 handoff symptoms
- HLD A1 implications
- current executor audit

Trigger:

- A1 implementation planning.

### Q3. Which existing policy classes should survive?

Recommended default:

```text
Keep only policy code that can become a small transition rule under SetupTurnLoop. Collapse or delete policy code that exists only to compensate for missing output inspection, event visibility, or capability-plan boundaries.
```

Source:

- grill decision correction
- grounding matrix section on TurnLoop

Trigger:

- A1 touches `policies.py`.

### Q4. When should `setup.world_background.*` be exposed?

Recommended default:

```text
Do not expose it in the B tool-protocol slice by default. Keep provider-side
candidate code hidden by CapabilityPlan snapshots until a separate
product/tool feature slice explicitly accepts a stage-local CRUD family.
```

Source:

- current architecture audit candidate register
- tool-scope tests
- pi-mono `AgentContext.tools`: current tools are selected into context rather than hardwired into the loop
- Claude Code tool pool filtering / fail-closed defaults

Trigger:

- a future product slice explicitly wants `setup.world_background.*` or another stage-local CRUD family to become model-visible.

### Q5. Which provider docs must be checked?

Recommended default:

```text
Check official OpenAI and Anthropic docs only when implementation relies on concrete tool-call, structured-output, streaming, or schema-compatibility behavior. Do not cite memory for exact API fields.
```

Source:

- PRD authority order
- HLD ModelGateway primary-doc rule

Trigger:

- A1/A4 implementation specifies concrete provider request/response fields or stream chunk parsing behavior.

### Q6. Should this become a project-level runtime core for future agents?

Recommended default:

```text
Design contracts as project-level runtime concepts, but implement only the SetupAgent path now. Do not generalize before one setup path is correct and tested.
```

Source:

- user wants architecture improvement, not a framework rewrite
- pi-mono minimal vocabulary is reusable
- current product contracts are setup-specific

Trigger:

- A1/A2 extraction starts creating package-level modules outside setup-specific runtime.

### Q7. Should SetupAgent call retrieval-core / Memory OS to recover setup draft truth?

Recommended default:

```text
No. SetupAgent uses setup-owned readback for prestory editing:
setup.read.draft_refs for current editable draft refs, and
setup.truth_index.search/read_refs for accepted committed setup truth.
Retrieval-core starts after accepted setup truth is materialized into seed
sections and then owns chunking, embeddings, hybrid/rerank, Recall/Archival
search, and active-story runtime retrieval.
```

Source:

- active `rp-setup-agent-stage-local-context-governance` spec
- active `rp-setup-truth-index-foundation` spec
- active `rp-setup-retrieval-seed-materialization` spec
- pi-mono selected context/tools boundary
- Claude Code context engineering and explicit readback/tool-result separation

Trigger:

- a future product slice wants semantic search during setup editing, wants a new model-visible setup retrieval tool, or wants retrieval readiness to affect setup commit/stage progression.

## 4. Non-Questions

Do not ask these again unless new evidence contradicts the current docs:

- Whether current code can be used for product semantics: yes.
- Whether current code boundaries should be preserved by default: no.
- Whether standard model tool calling remains: yes.
- Whether prompt can open a tool by itself: no.
- Whether `SetupWorkspace` remains business truth: yes.
- Whether runtime trace/cognition becomes product truth by default: no.
- Whether A1 should add subagents: no.
- Whether C adds RAG/embedding to SetupAgent by default: no.
- Whether Memory OS / retrieval-core should recover current editable setup draft truth by default: no.
- Whether SkillPack can control tools, business state, runtime overlay,
  `context_bundle`, or durable runtime state: no. SkillPack is stable
  prompt/context packaging plus metadata-only observability.
- Whether SkillPack activation needs another `$grill-me` question in D: no.
  The current docs/code/pi-mono/Claude Code rationale converge on deterministic
  stage-keyed activation and hard-unload.

## 5. Question Handling Rule

When a real design question appears:

1. First check current code/spec/reference evidence.
2. If references converge and do not alter setup product semantics, recommend a default instead of asking open-endedly.
3. If the choice changes product semantics, ask one precise `$grill-me` question.
4. Write the answer back into this task's docs immediately.
