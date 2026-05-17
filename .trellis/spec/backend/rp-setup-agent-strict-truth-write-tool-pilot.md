# RP Setup Agent Slim Truth Write Tool Surface

> Historical/deprecated note. This pilot described the former model-facing `setup.truth.write` slim-schema adapter. M9 removed `setup.truth.write` from the SetupAgent provider/model tool chain.

## Current Status

- `setup.truth.write` is no longer registered as a SetupAgent tool, no longer appears in provider `list_tools()`, schema maps, handler maps, runtime allowlists, prompt guidance, or model requests.
- The runtime no longer owns a truth-write slim-schema adapter, strict-tool toggle, or argument rehydration path for `setup.truth.write`.
- Three canonical draft stages use the current-stage CRUD tools instead:
  - `world_background` -> `setup.stage_entry.*` writes `workspace.draft_blocks["world_background"]`
  - `character_design` -> `setup.stage_entry.*` writes `workspace.draft_blocks["character_design"]`
  - `plot_blueprint` -> `setup.stage_entry.*` writes `workspace.draft_blocks["plot_blueprint"]`
- Backend services may still contain lower-level draft mutation helpers for UI/service workflows. Those helpers are not agent tools and must not be re-exposed as a fallback.

## Historical Boundary

Historical eval traces, diagnostics fixtures, or old migration notes may still contain the literal string `setup.truth.write`. Those strings are not current provider/scope/prompt/schema/handler contracts.

## Current Guardrail

Any future change touching SetupAgent draft writes must treat `setup.stage_entry.*` as the current model-facing draft CRUD surface. Reintroducing `setup.truth.write` as an agent tool requires a new explicit product decision and a new spec.
