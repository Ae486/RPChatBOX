# Structured Output Provider Notes - 2026-04-30

## Scope

This note records the current provider evidence for the SetupAgent
`setup.truth.write` strict-tool pilot.

Sources are separated by type:

- Real-chain test: local `H:/chatboxapp` SetupAgent runtime with the configured
  local provider/model registry.
- Official docs: provider-owned documentation for DeepSeek and GLM/Z.ai.
- Engineering judgment: implications for the current strict-tool pilot.

## Real-Chain Test: Bohe Gemini 2.5 Flash

Provider/model under test:

- provider_id: `39a5de23-0c64-4711-87bc-d69667e53f0d`
- provider name: Bohe
- api_url: `https://x666.me/v1/chat/completions`
- model_id: `45776d28-7975-4a4b-8fb3-4cca18daeb02`
- model_name: `gemini-2.5-flash`

### Strict Pilot Probe

Command intent:

- Run `test_real_model_strict_truth_write_accepts_slim_schema` against Bohe
  `gemini-2.5-flash`.

Result:

- The test failed before reaching the remote model.
- Failure reason: current runtime did not attach `function.strict = true` to
  `setup.truth.write` for `gemini-2.5-flash`.
- This is expected under the current spec because the strict slim schema pilot
  is gated to GPT/Codex-family model names until provider capability metadata
  exists.

Observed schema shape:

- `setup.truth.write` was visible.
- `strict` was absent.
- The full provider schema was exposed, including `workspace_id` and `step_id`.

Conclusion:

- This failure is not evidence that the Bohe channel or Gemini model rejects
  tool calls.
- It only confirms the earlier strict pilot gate left Gemini on the non-strict
  full-schema path.
- Follow-up design changed this: non-strict providers should still receive the
  slim model-facing schema when runtime defaults are available; only the
  `function.strict` flag stays gated.

### Full-Schema Tool-Calling Scenario

Scenario:

1. User asks SetupAgent to create a foundation draft entry.
2. Model must call `setup.truth.write`.
3. Runtime persists the draft.
4. User later asks for an exact detail that is not present in compacted prompt
   history but is present in the draft.
5. Model must call `setup.read.draft_refs`.
6. Runtime returns the exact draft detail and model answers with it.

Result:

- Write turn completed.
- `setup.truth.write` was called once and succeeded.
- Draft contained `foundation:magic-law`.
- Stored exact summary: `Public spellcasting requires guild permits.`
- Recovery turn used compact context:
  - `context_profile = compact`
  - `compacted_history_count = 8`
  - the exact detail was not visible in the pre-tool recovery request
- `setup.read.draft_refs` was called with:
  - `refs = ["foundation:magic-law"]`
  - `detail = "full"`
- Read tool succeeded.
- Final answer contained the exact recovered detail.

Conclusion:

- Bohe `gemini-2.5-flash` can execute the current SetupAgent full-schema tool
  chain for this scenario.
- This validates the channel/model for non-strict tool calls in the compact
  recovery path.
- This does not prove that Gemini should be added to the strict slim-schema
  pilot.

## Official Docs: DeepSeek

Official sources:

- Function calling: https://api-docs.deepseek.com/guides/function_calling/
- JSON output: https://api-docs.deepseek.com/guides/json_mode/

### Function Calling

Documented behavior:

- DeepSeek exposes OpenAI-compatible `tools` function calling.
- Strict mode is marked Beta.
- Strict mode requires using the beta endpoint base URL:
  `https://api.deepseek.com/beta`.
- For strict mode, all functions in the request's `tools` parameter must set
  `strict = true`.
- `strict = true` should be set inside each function definition.
- DeepSeek documents a supported JSON Schema subset for strict mode.

Relevant constraint for current SetupAgent:

- The current pilot sets strict only on the slim `setup.truth.write` model-facing
  schema and intentionally leaves other setup tools non-strict.
- That shape does not match DeepSeek strict-mode docs if multiple tools are sent
  in the same request.

### JSON Output

Documented behavior:

- JSON mode is enabled with `response_format = {"type": "json_object"}`.
- The prompt should explicitly instruct the model to output JSON.
- JSON mode is separate from function calling.

Implication:

- DeepSeek JSON mode is not a direct replacement for tool-call argument
  strictness.
- For `setup.truth.write`, the safer path is still tool calling plus pydantic
  validation and repair.

## Official Docs: GLM / Z.ai

Official sources:

- Function calling: https://docs.z.ai/guides/capabilities/function-calling
- Structured output: https://docs.z.ai/guides/capabilities/struct-output
- Chat completion API: https://docs.z.ai/api-reference/llm/chat-completion
- Chinese capability guide: https://docs.bigmodel.cn/cn/guide/capabilities/function-calling

### Function Calling

Documented behavior:

- GLM/Z.ai supports function calling through OpenAI-style `tools`.
- Tool definitions include function `name`, `description`, and JSON-Schema-like
  `parameters`.
- Tool choice is documented primarily as `auto`.
- The docs emphasize feeding tool execution results back to the model for final
  answer generation.

### Structured Output

Documented behavior:

- The chat completion API supports `response_format`.
- JSON mode is represented as `{"type": "json_object"}`.
- The docs recommend combining JSON mode with clear prompt instructions.
- The structured-output guide shows JSON Schema validation as application-side
  validation after parsing JSON mode output, not as an API-level
  `json_schema` response format.

Not found in official docs during this pass:

- A documented `tools[].function.strict = true` contract equivalent to OpenAI
  strict tools or DeepSeek beta strict mode.
- A documented `response_format = {"type": "json_schema", ...}` contract for
  the GLM chat completion endpoint.

Implication:

- GLM should not be added to the strict slim-schema gate based only on docs.
- Treat GLM as OpenAI-compatible tool calling with provider-side schema hints,
  then rely on pydantic validation and the bounded repair loop.
- If GLM is later considered for strict mode, it should be gated by a real
  request/response capability probe, not by model-family name.

## Engineering Judgment

Current strict gate should remain conservative:

- Keep strict slim `setup.truth.write` enabled only for GPT/Codex-family models
  with verified real-chain evidence.
- Keep Gemini, GLM, DeepSeek, and similar OpenAI-compatible providers on the
  non-strict slim-schema path when runtime defaults are available.
- Keep the full provider schema as fallback only when runtime defaults are not
  available or a provider-specific compatibility issue is proven.

Do not directly expand strict mode to DeepSeek yet:

- DeepSeek strict mode is beta-endpoint specific.
- It requires all request functions to be strict, while the current pilot is
  intentionally one-tool-only.

Do not directly expand strict mode to GLM yet:

- Official GLM/Z.ai docs confirm tool calling and JSON mode, but this pass did
  not find a documented strict-tool contract.

Recommended next step:

- Add provider/model capability metadata such as `supports_strict_tools`,
  `strict_tools_requires_all_tools`, and `strict_tools_endpoint_requirement`
  before expanding the pilot beyond GPT/Codex.
- Keep real-model probes provider-specific and opt-in.

## 2026-04-30 Follow-Up: Base Path Must Be Strong

User-confirmed product/engineering requirement:

- The common structured-output path must itself be highly constrained.
- Provider-specific request parameters such as `function.strict`,
  `response_format=json_object`, or `response_format=json_schema` are
  enhancements, not the foundation of correctness.

Practical interpretation for `setup.truth.write`:

- The model-facing slim schema and runtime-owned field injection should be the
  default when the runtime can determine the current setup step.
- `function.strict = true` is only an extra request flag for verified model
  families or future capability metadata.
- The full provider schema remains a fallback only when runtime-owned defaults
  cannot be determined.

Real-chain addendum:

- Bohe `gemini-2.5-flash` rejected the first slim schema because `target_ref`
  used the JSON Schema union type `["string", "null"]`.
- The gateway error came from Gemini native tool schema conversion, not from
  SetupAgent pydantic validation.
- To keep the common base path portable, the slim model-facing schema should use
  `target_ref: string` with `""` meaning no target, and runtime should normalize
  that back to provider-side `None`.

Source split:

- Current implementation: provider-side `SetupTruthWriteInput` and pydantic
  validation are unchanged and remain final truth.
- Current real-model evidence: missing `step_id` / `block_type` is a model
  burden problem; slimming the model-facing schema reduces the burden without
  relying on strict.
- LiteLLM/New API docs: they can forward or adapt OpenAI-compatible parameters,
  but they do not prove every downstream model/channel honors strict semantics.
- Engineering judgment: keep one base pipeline with capability-based
  enhancements rather than separate provider-specific execution chains.
