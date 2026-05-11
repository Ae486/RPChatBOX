# SetupAgent Current Gap Analysis

> Task-local analysis of current shortcomings and directions that need correction.

## 1. Executive Summary

The current SetupAgent implementation has many advanced pieces, but it is over-composed around internal nodes and under-specified around the agent loop contract. The result is a system that can look sophisticated while still failing core agent behavior:

- fake tool code can leak as normal assistant text
- recoverable tool errors can become final explanations too early
- successful tool results can fail to terminate cleanly
- tool surfaces are too overlapping for stage draft writing
- prompt/schema/tool/runtime responsibilities are mixed

The next slice should optimize the architecture spine first, not add more features.

## 2. What Is Already Useful

| Existing part | Value |
| --- | --- |
| `setup_graph_runner.py` / `setup_graph_nodes.py` | Thin outer shell already exists and can remain. |
| `setup_agent_execution_service.py` | Good place for session/context boundary, context budget, and stream coordination. |
| `agent_runtime/executor.py` | Already contains goal, plan, request, tool, assess, reflect, finalize concepts. |
| `policies.py` | Existing policy layer can host clearer repair/decision contracts. |
| `profiles.py` | Current tool-scope narrowing is the right direction. |
| `setup_tool_provider.py` | Provider-side pydantic validation and workspace mutation already provide deterministic authority. |
| `setup_agent_prompt_service.py` | Stage overlay and SkillPack injection already exist. |
| typed SSE tests | Existing event surface should be preserved, not replaced. |

## 3. Current Shortcomings

### 3.1 Architecture Is Node-Rich But Spine-Poor

The inner runtime has many nodes (`derive_turn_goal`, `plan_step_slice`, `build_model_request`, `inspect_model_output`, `execute_tools`, `apply_tool_results`, `assess_progress`, `reflect_if_needed`, finalize), but the high-level loop contract is not obvious enough.

Needed correction:

- define the loop as model -> inspect -> tool -> observation -> decision
- make every continuation reason explicit
- make stop reasons testable
- keep LangGraph as implementation mechanism, not the architecture vocabulary

### 3.2 Tool Output And Assistant Text Boundaries Are Weak

Observed failure: the model produced `tool_code print(default_api.rp_setup__setup.truth.write(...))` as text. That means either:

- real tool-call schema was not usable for that provider/model turn
- tool prompt/schema confused the model
- output inspection/frontend filtering did not catch internal pseudo tool content

Needed correction:

- provider/tool capability must be visible before request
- pseudo tool output must be classified by output inspector
- action expectations must decide whether pseudo tool text becomes repair or failure
- frontend must only render typed tool traces as tool events, not raw internal code as assistant content

### 3.3 Repair Loop Is Too Weak

Observed failure: after validation/provider errors, the agent often explains the error instead of correcting and retrying.

Needed correction:

- validation errors must become tool-result observations
- next model call must include concise repair hints
- recoverable errors should be withheld from final user-visible failure until budget is exhausted
- repeated same error must stop with `fail_retry_budget`, not recurse

### 3.4 Stop/Continue Routing Is Underspecified

Observed failure: `discussion.update_state` tool call produced start/result events, then graph ran until recursion limit.

Needed correction:

- tool success must route to deterministic `finish_tool_success`, `continue_next_action`, or `ask_user`
- no-progress and same-state loops must be detected before LangGraph limit
- graph recursion limit is a safety fuse only

### 3.5 Draft Tool Contract Is In Conflict

User direction now favors:

- stage-native deterministic CRUD tools
- LLM fills simple content parameters
- tool code owns entry shape, IDs, type registry, metadata normalization, merge/delete

The selected direction is a shared CRUD core exposed through stage-local SkillPack/prompt packaging. Legacy conflicting write paths may be retired after the new tool set proves stable in tests.

### 3.6 Feature Scope Drift

Model config sync and dialogue persistence are useful, but they are not the core architecture-spine bug. They should be deferred unless they become necessary to prove the spine.

### 3.7 SkillPack Pilot Drift

Current SkillPack spec/demo is character-stage oriented. Expanding SkillPacks to every setup stage is plausible, but should not be bundled into the loop/tool repair slice.

## 4. Directions To Stop

Stop doing these in this task:

- adding more tools before resolving canonical write surface
- treating prompt wording as the main fix for schema failure
- using LangGraph node proliferation as architecture clarity
- mixing model page sync, dialogue persistence, SkillPack expansion, and tool repair into one implementation slice
- letting task-local plan override setup executable specs without explicit update

## 5. Directions To Take

Do these instead:

1. Freeze the architecture spine.
2. Implement/verify output inspection and decision policy around pseudo tool text, repair, and stop.
3. Resolve the stage draft write contract.
4. Only then simplify stage tool surfaces.
5. Keep typed SSE and visible/internal separation intact.
6. Run focused tests before any live model smoke.

## 6. Grill Queue Candidates

These are real design questions, not implementation uncertainties:

- Should stage-native CRUD replace `setup.truth.write` as the model-visible write surface, or should it be implemented behind/inside the truth-write adapter?
- Should all stages share one draft CRUD core with stage-native aliases, or should each stage own different write tools?
- Where should stage-local `entry_type` registry live: draft schema metadata, workspace transient state, or tool-runtime state?
- Should setup visible dialogue persistence be part of this task or a follow-up task after loop spine stabilizes?

## 7. A1 Correction Note

The A1 check correction keeps world_background CRUD out of the A1 visible/runtime surface. Stage-local world_background CRUD tooling is not registered in `SetupToolProvider`, is not included in `SETUP_AGENT_VISIBLE_TOOLS`, is not returned by `build_setup_agent_tool_scope(...)`, and is not part of A1 tests. Canonical stages still expose shared setup tools such as `setup.truth.write`, `setup.question.raise`, `setup.proposal.commit`, and setup read helpers.

The correction also adds explicit terminal reasons for bounded bad paths before LangGraph recursion is relevant:

- repeated pseudo tool-call text: `invalid_tool_output_retry_budget_exhausted`
- repeated same-class recoverable tool failure: `tool_recovery_budget_exhausted`

These are task-local A1 stop reasons for current check closure. If they are kept beyond this task, the global loop-semantics spec taxonomy should be updated in a later spec-sync slice.
