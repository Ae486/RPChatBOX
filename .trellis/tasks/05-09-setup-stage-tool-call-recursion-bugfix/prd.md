# Setup Stage Tool Call And Recursion Bugfix PRD

> Task: `.trellis/tasks/05-09-setup-stage-tool-call-recursion-bugfix`
>
> Status: active
>
> Current priority: agent architecture optimization first. Setup retrieval, draft CRUD migration, SkillPack expansion, model-page sync, and dialogue persistence are follow-up module/function optimizations unless required to validate the agent spine.

## Problem

Manual setup testing exposed two architecture-level failures:

1. SetupAgent can output pseudo tool code such as `tool_code print(default_api.rp_setup__setup.truth.write(...))` as visible assistant text instead of issuing a real tool call.
2. After a real setup tool call succeeds, the setup graph can continue until LangGraph raises `GRAPH_RECURSION_LIMIT`, which means the agent loop lacks a reliable stop/continue contract.

These are not isolated prompt issues. They show that model output inspection, tool execution, repair policy, stop decisions, and user-visible events are not separated strongly enough.

## Goal

Make SetupAgent a reliable creative-agent loop reference implementation:

```text
context -> model -> inspect output -> execute tools -> observe result -> decide repair/continue/finish/fail -> emit clean events
```

This task should make the agent loop robust enough that later setup modules, retrieval, draft CRUD, and runtime-story agents can reuse the same architectural primitives.

## Non-Goals

- Do not modify runtime-story-dev Q documents, Q acceptance tests, or runtime-story implementation as part of this task.
- Do not complete the full setup retrieval roadmap in the A1 slice.
- Do not migrate every setup stage to the final unified draft CRUD contract in the A1 slice.
- Do not expand SkillPacks to every stage in the A1 slice.
- Do not treat LangGraph recursion limit as a valid business stop condition.

## Users And Use Cases

- Setup users want to discuss a stage, have the agent write or edit drafts through real tools, and never see internal pseudo tool code.
- Developers need a testable agent loop whose bad paths are deterministic.
- Later runtime-story work needs a reusable agent spine for model/tool/repair/event behavior.

## Functional Requirements

### A1 Agent Loop Spine

- Pseudo tool-call text must not be delivered as ordinary assistant content when a tool call is required or clearly attempted.
- Real tool calls must execute through the setup tool runtime and emit typed tool start/result events.
- Tool validation/provider failures that are recoverable must become repair observations before final failure.
- Repeated same-class recoverable failures must stop with an explicit retry-budget failure.
- Successful setup tool results must route to a deterministic next state: finish, ask user, continue with a named obligation, or fail.
- Every iteration must produce one explicit decision surface:
  - `continue_reason`
  - `finish_reason`
  - `failure_reason`
- Typed SSE tool events must remain visible while internal trace/debug/pseudo tool text stays out of assistant content.

### Later Module Work, Not A1 Completion

- Setup lightweight retrieval remains setup-owned and uses draft refs / setup truth index before retrieval-core materialization.
- Unified draft CRUD remains the target model-facing direction, but full migration is not required to complete A1.
- SkillPacks remain stage-local prompt packs and must not become hidden business-contract owners.

## Architecture Direction

LangGraph remains allowed as the execution/checkpoint/streaming substrate. The SetupAgent product semantics should be expressed above it:

```text
SetupAgentSession
  -> SetupTurnLoop
      -> SetupContextPipeline
      -> ModelGateway
      -> OutputInspector
      -> SetupToolRuntime
      -> DecisionPolicy
      -> SetupEventSink
```

Existing services and tests should be reused where possible. Refactoring must be incremental and should preserve frozen setup contracts.

## Acceptance Criteria

- Focused tests cover pseudo tool text handling, recoverable tool validation repair, repeated failure budget exhaustion, successful tool result stop/next routing, and typed SSE preservation.
- A setup turn cannot rely on `GRAPH_RECURSION_LIMIT` as its intended stop mechanism.
- `git diff --name-only` confirms no runtime-story Q docs/tests/implementation were modified by this task slice.
- Module-level `trellis-check` is run after A1 implementation completes.

## Open Follow-Ups

- Full setup retrieval roadmap: R0-R5 as recorded in task research docs.
- Unified draft CRUD migration and legacy tool retirement.
- Setup dialogue persistence.
- Setup model configuration page synchronization.
- SkillPack governance and stage expansion.
