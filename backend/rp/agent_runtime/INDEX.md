# rp.agent_runtime ownership index

`backend/rp/agent_runtime/` is physically split into three implementation
zones. Runtime implementation work belongs in `kernel/`, `setup/`, or `story/`;
the package root contains only package/documentation files.

| Path | Zone | Ownership |
|---|---|---|
| `kernel/state.py` | `[KERNEL-shared]` | Shared run-state substrate for setup and story runtime paths. |
| `kernel/graph.py` | `[KERNEL-shared]` | Shared LangGraph wiring over the runtime state. |
| `kernel/runtime_tool_contracts.py` | `[KERNEL-shared]` | Shared tool call/result contracts. |
| `setup/contracts.py` | `[SETUP-only]` | Setup runtime contracts; may re-export kernel tool contracts. |
| `setup/executor.py` | `[SETUP-only]` | Setup runtime executor. |
| `setup/policies.py` | `[SETUP-only]` | Setup runtime policy helpers. |
| `setup/adapters.py` | `[SETUP-only]` | Setup-side runtime adapters. |
| `setup/profiles.py` | `[SETUP-only]` | Setup capability/profile composition. |
| `setup/events.py` | `[SETUP-only]` | Setup runtime event payloads/adapters. |
| `setup/tools.py` | `[SETUP-only]` | Setup-side runtime tool execution surface. |
| `setup/prompts/` | `[SETUP-only]` | SetupAgent prompt text and prompt accessors. |
| `setup/skill_packs/` | `[SETUP-only]` | SetupAgent stage SkillPack registry and assets. |
| `story/story_harness.py` | `[STORY-only]` | Story harness substrate over the shared kernel. |

## Decoupling rules

1. Kernel files (`kernel/state.py`, `kernel/graph.py`,
   `kernel/runtime_tool_contracts.py`) must not import setup-private files,
   story-private files, `rp.services.*`, or `rp.models.setup_agent.*`.
2. Setup-private files under `setup/` and `rp.services.setup_agent.*` must not
   import `rp.agent_runtime.story.story_harness`.
3. `story/story_harness.py` may import only kernel files from `rp.agent_runtime`;
   it must not import setup-private files or `rp.services.setup_agent.*`.

## Maintenance note

Kernel changes affect both setup and story paths, so review both callers.
Setup-only and story-only changes should remain isolated. The deterministic
`check_agent_runtime_zone_boundary` lint enforces this boundary in CI.

`kernel/state.py` still contains `cognitive_state` and
`cognitive_state_summary` TypedDict keys. They are setup-oriented slots retained
in the shared state shape; the story driver does not write them.
