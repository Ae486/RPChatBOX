# rp.agent_runtime ownership index

`backend/rp/agent_runtime/` contains three intentionally co-located runtime
concerns. Keep the ownership boundary explicit before changing imports.

| File | Zone | Ownership |
|---|---|---|
| `state.py` | `[KERNEL-shared]` | Shared run-state substrate for setup and story runtime paths. |
| `graph.py` | `[KERNEL-shared]` | Shared LangGraph wiring over the runtime state. |
| `runtime_tool_contracts.py` | `[KERNEL-shared]` | Shared tool call/result contracts. |
| `contracts.py` | `[SETUP-only]` | Setup runtime contracts; may re-export kernel tool contracts. |
| `executor.py` | `[SETUP-only]` | Setup runtime executor. |
| `policies.py` | `[SETUP-only]` | Setup runtime policy helpers. |
| `adapters.py` | `[SETUP-only]` | Setup-side runtime adapters. |
| `profiles.py` | `[SETUP-only]` | Setup capability/profile composition. |
| `events.py` | `[SETUP-only]` | Setup runtime event payloads/adapters. |
| `tools.py` | `[SETUP-only]` | Setup-side runtime tool execution surface. |
| `story_harness.py` | `[STORY-only]` | Story harness substrate over the shared kernel. |

## Decoupling rules

1. Kernel files (`state.py`, `graph.py`, `runtime_tool_contracts.py`) must not
   import setup-private files, `story_harness.py`, `rp.services.*`, or
   `rp.models.setup_agent.*`.
2. Setup-private files and `rp.services.setup_agent.*` must not import
   `rp.agent_runtime.story_harness`.
3. `story_harness.py` may import only kernel files from `rp.agent_runtime`; it
   must not import setup-private files or `rp.services.setup_agent.*`.

## Maintenance note

Kernel changes affect both setup and story paths, so review both callers.
Setup-only and story-only changes should remain isolated. The deterministic
`check_agent_runtime_zone_boundary` lint enforces this boundary in CI.

`state.py` still contains `cognitive_state` and `cognitive_state_summary`
TypedDict keys. They are setup-oriented slots retained in the shared state
shape; the story driver does not write them.
