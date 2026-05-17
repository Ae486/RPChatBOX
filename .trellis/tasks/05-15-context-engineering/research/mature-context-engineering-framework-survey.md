# Mature Context Engineering Framework Survey

> Task: `.trellis/tasks/05-15-context-engineering`
>
> Status: research-v1
>
> Date: 2026-05-16

## 1. Conclusion

A good Context Engineering module is not a "summary service" and not a thin
wrapper around the current SetupAgent context code.

It is the pre-model-call governance layer that turns many possible sources into
a bounded, provider-compatible, traceable model input:

```text
select sources
-> normalize source items
-> apply visibility / policy / budget
-> preserve recent raw windows
-> compress or summarize older/noisy material
-> validate refs and schema
-> serialize sections in cache-aware order
-> emit trace / usage / read manifest / recovery refs
```

For RP, the authoritative design references should be mature agent systems and
professional AI platform guidance. SetupAgent is only a proving ground. Current
setup services are workload evidence and migration material; they may be
optimized, replaced, or removed if they conflict with the common module design.

## 2. Mature Reference Lessons

### 2.1 Claude Code / Claude Code From Scratch

Local references:

- `docs/research/how-claude-code-works-main/docs/03-context-engineering.md`
- `docs/research/how-claude-code-works-main/docs/08-memory-system.md`
- `docs/research/how-claude-code-works-main/docs/09-skills-system.md`
- `docs/research/claude-code-from-scratch-main/docs/07-context.md`
- `docs/research/claude-code-from-scratch-main/docs/08-memory.md`
- `docs/research/claude-code-from-scratch-main/docs/09-skills.md`
- `docs/research/claude-code-from-scratch-main/src/prompt.ts`
- `docs/research/claude-code-from-scratch-main/src/session.ts`

Key lessons:

- Every API call is assembled deliberately. The context layer owns the request
  surface; it does not rely on the model "remembering".
- Prompt sections have different stability classes. Stable system/developer
  instructions, user/project rules, memory indexes, skill manifests, recent
  messages, tool observations, and compact summaries should not be mixed into
  one untyped blob.
- Compression is progressive. Mature systems shrink large tool results, snip
  stale observations, run idle or pressure-based compact, and use full
  autocompact only when cheaper measures are insufficient.
- Compact is a pre-model operation. It does not mutate business truth.
- Recovery is first-class. Summaries should carry refs or manifests for exact
  detail recovery because compression is lossy.
- Memory and skills are context-governance examples:
  - memory uses a loaded index plus lazy exact payload reads;
  - skills use discovery metadata first, then load full instructions only when
    selected;
  - forked skill/subagent execution isolates heavy or risky context from the
    main thread.
- Prompt assembly should support include expansion, circular guards, section
  ordering, environment/git context, and explicit dynamic sections.

RP implication:

The common module needs typed section/source contracts, not just message
trimming. It must track placement, stability, visibility, source refs, recovery
refs, fallback, and trace.

### 2.2 pi-mono

Local references:

- `docs/research/pi-mono-main/packages/coding-agent/docs/compaction.md`
- `docs/research/pi-mono-main/packages/coding-agent/docs/session.md`
- `docs/research/pi-mono-main/packages/coding-agent/docs/skills.md`
- `docs/research/pi-mono-main/packages/coding-agent/src/core/compaction/compaction.ts`
- `docs/research/pi-mono-main/packages/coding-agent/src/core/compaction/utils.ts`
- `docs/research/pi-mono-main/packages/coding-agent/src/core/session-manager.ts`
- `docs/research/pi-mono-main/packages/coding-agent/src/core/agent-session.ts`
- `docs/research/pi-mono-main/packages/ai/src/utils/overflow.ts`
- `docs/research/pi-mono-main/packages/ai/src/providers/anthropic.ts`
- `docs/research/pi-mono-main/packages/ai/src/providers/openai-responses-shared.ts`
- `docs/research/pi-mono-main/packages/ai/test/context-overflow.test.ts`

Key lessons:

- Session persistence and model-visible context are separate. A JSONL tree stores
  all entries; `buildSessionContext()` walks the current branch and resolves the
  model-visible sequence.
- Compaction is represented as a durable entry with `summary`,
  `firstKeptEntryId`, `tokensBefore`, and optional details. The summary becomes a
  context artifact; raw history still exists in session storage.
- Auto-compaction uses a policy boundary:
  `contextTokens > contextWindow - reserveTokens`.
- Recent work is preserved by finding a cut point from newest messages backward.
  The default policy keeps a recent token window and avoids cutting at tool
  results so tool-call/result pairing remains valid.
- Long single turns need split-turn handling. pi-mono can summarize the early
  part of a turn while retaining the suffix.
- Branch navigation has its own summarization path. When leaving a branch, it
  can summarize the abandoned path and inject a branch summary at the new point.
- File operation tracking accumulates through compactions and branch summaries.
  This is a concrete recovery-manifest pattern.
- Summarization serializes prior conversation as data, not as a conversation to
  continue, and truncates large tool results before asking the model to
  summarize.
- Extension hooks can cancel compaction or provide custom summaries. This is a
  mature example of common kernel plus adapter/custom policy.
- Provider overflow behavior is normalized across Anthropic, OpenAI, Google,
  OpenRouter, local models, and others. Context governance must understand
  provider-specific failure modes and silent truncation risks.
- Provider adapters transform message formats, cache controls, thinking blocks,
  tool calls, and tool results. Context Engineering must output a canonical
  packet that can still be adapted per provider.

RP implication:

The RP common module should separate persisted state, source selection, compact
artifacts, provider serialization, and runtime retry/overflow recovery. pi-mono
also shows why branch-aware RP runtime cannot rely on a linear transcript model.

### 2.3 OpenAI

External references:

- Conversation State: <https://platform.openai.com/docs/guides/conversation-state?api-mode=responses>
- Compaction: <https://developers.openai.com/api/docs/guides/compaction>
- Prompt Caching: <https://platform.openai.com/docs/guides/prompt-caching>
- Agents SDK Sessions: <https://openai.github.io/openai-agents-python/sessions/>

Key lessons:

- Provider-managed state is convenience, not product truth. `previous_response_id`
  or hosted conversation state can reduce client-side message handling, but RP
  still needs explicit policy over branch visibility, prompt sections, and truth
  boundaries.
- Compaction is a continuation artifact that preserves useful state under token
  pressure. It should not be treated as canonical domain data.
- Prompt caching rewards stable prefix ordering. Stable instructions and tools
  should stay early; volatile request state and summaries should be later.
- Sessions in an agent SDK separate stored history from agent runs. Compaction
  wrappers can apply threshold logic around session history.

RP implication:

The common module should support provider-managed conversation state only as an
optional provider feature. RP still owns budget, placement, cache-stable section
ordering, compact artifact metadata, and read manifest.

### 2.4 Anthropic / Claude Code Docs

External references:

- Effective Context Engineering for AI Agents: <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>
- Prompt Caching: <https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching>
- Context Windows: <https://docs.anthropic.com/en/docs/build-with-claude/context-windows>
- Claude Code Memory: <https://docs.anthropic.com/en/docs/claude-code/memory>

Key lessons:

- Context Engineering is attention-budget curation. It includes prompts, tools,
  retrieved information, memory, recent work, compacted state, and what is
  intentionally omitted.
- Compression quality should be tuned on complex traces. Start with high recall
  to avoid losing important facts, then improve precision to remove noise.
- Tool-result design is part of Context Engineering. Large or poorly structured
  tool outputs can damage agent quality even if summarization is good.
- Prompt caching requires explicit stable blocks and cache breakpoints.
- Claude Code memory reinforces the index-plus-content split and the idea that
  memory is editable project/user context, not unverified current truth.

RP implication:

The common module must expose source-family-specific policies. Setup tool
outcomes, Story accepted prose, retrieval cards, brainstorm turns, and review
overlays need different retention and compression rules.

### 2.5 Google Gemini / Vertex AI

External references:

- Gemini API Context Caching: <https://ai.google.dev/gemini-api/docs/caching>
- Gemini API Long Context: <https://ai.google.dev/gemini-api/docs/long-context>
- Gemini API Token Counting: <https://ai.google.dev/gemini-api/docs/tokens>
- Vertex AI Context Cache: <https://cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview>

Key lessons:

- Long context does not remove the need for context design. Large windows make
  it easier to include more material, but attention, latency, cost, cacheability,
  and exact source scope still matter.
- Context caching is a provider-level optimization for repeated stable content.
  The application must still decide which content is stable enough to cache.
- Token counting is an explicit engineering surface. Good context modules need
  estimation before calls and usage reconciliation after calls.
- Cached context and retrieval/grounding are not product truth. They are
  model-input mechanisms.

RP implication:

The RP module should support long-context models and caching, but the core
contract should still be budgeted, scoped, and traceable. Long-context support
is a policy mode, not permission to dump raw workspace state into prompts.

### 2.6 LangChain / LangGraph / Deep Agents

External references:

- LangChain Context Engineering: <https://docs.langchain.com/oss/python/langchain/context-engineering>
- LangChain Short-Term Memory: <https://docs.langchain.com/oss/python/langchain/short-term-memory>
- LangChain Context Engineering Blog: <https://blog.langchain.com/context-engineering-for-agents/>
- Deep Agents Context Engineering: <https://docs.langchain.com/oss/python/deepagents/context-engineering>

Key lessons:

- Mature framing separates write context, select context, compress context, and
  isolate context.
- Short-term thread state, runtime context, and long-term memory are different
  surfaces.
- Middleware before model calls can trim messages, summarize, alter prompts,
  select tools, or change response formats.
- Deep agents use three strong isolation/offloading patterns: filesystem-backed
  state for large artifacts, todo/planning tools for task state, and subagents
  with their own context windows.

RP implication:

The common module should be pre-model middleware with typed operation contracts.
It should support isolation between setup turns, writer packets, worker packets,
brainstorm windows, review sidecars, and future specialist agents.

### 2.7 Manus

External reference:

- Context Engineering for AI Agents: <https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus>

Key lessons:

- Stable prompt prefixes matter for cache reuse.
- Append-only and deterministic context serialization reduces drift.
- Avoid irreversible compression when exact details may be needed later.
- Externalized memory/files can be a stronger long-horizon substrate than
  keeping everything in the live context window.

RP implication:

The common module should prefer deterministic section ordering, omitted-source
records, and recovery refs over untraceable deletion.

## 3. What A Good RP Context Engineering Module Looks Like

### 3.1 Core Ownership

The common kernel owns reusable mechanics:

- source item normalization;
- source family / visibility / stability classification;
- token and character estimation;
- budget profiles and recent-window retention;
- deterministic selection, omission, and ordering;
- source fingerprinting and compact artifact reuse checks;
- compact / summary prompt invocation through an injected model gateway;
- structured output validation through adapter-provided schemas;
- forbidden-field and ref validation;
- deterministic fallback artifacts;
- provider-neutral context packet serialization;
- usage capture and post-call reconciliation;
- trace, read manifest, selected/omitted/hidden-source reports;
- overflow detection and retry/compact recommendations.

### 3.2 Adapter Ownership

Each runtime adapter owns semantics:

- source discovery and visibility scope;
- which raw windows cannot be compacted;
- which schema is expected from a summary;
- which refs are recoverable, hidden, or forbidden;
- where compact artifacts are placed;
- whether failure means fallback, skip, fail closed, or user-facing error;
- whether any output is allowed to become product truth.

The default product rule should be:

```text
Context Engineering output is model-input support, not truth mutation.
```

Truth mutation requires a separate governed apply path.

### 3.3 Suggested Package Shape

The first implementation should aim for an independently understandable common
module, for example:

```text
backend/rp/context_engineering/
  contracts.py        # SourceItem, OperationRequest, OperationResult, reports
  policies.py         # budget/window/source-family policies
  normalization.py    # adapter source -> normalized source item helpers
  selection.py        # deterministic selection/omission/order
  compaction.py       # compact prompt request/reuse/fallback
  validation.py       # schema/ref/forbidden-field checks
  serialization.py    # provider-neutral packet sections
  tracing.py          # usage/read manifest/context report builders
  overflow.py         # provider overflow classification/recovery signals

backend/rp/context_engineering/adapters/
  setup.py            # setup proving-ground adapter
  story_writer.py     # future writer packet adapter
  story_worker.py     # future worker packet adapter
  brainstorm.py       # future brainstorm summarization adapter
```

This package should not import setup workspace models, story Core State mutation
services, Memory OS writers, UI contracts, or tool providers. Adapters may import
domain services and map them into common contracts.

### 3.4 Canonical Operation Model

A practical operation contract should include:

- `operation_id`: stable trace id.
- `operation_kind`: `trim`, `compact`, `summarize`, `packet_build`,
  `trace_only`.
- `source_items`: normalized inputs.
- `budget_policy`: context window, response reserve, source family caps,
  recent-window caps.
- `placement_policy`: stable prefix, dynamic context, recent raw, compact,
  retrieval, tool outcomes, debug-only.
- `validation_policy`: schema, forbidden fields, allowed ref families.
- `fallback_policy`: deterministic fallback, skip, fail closed.
- `provider_profile`: model context window, cache support, reasoning/thinking
  behavior, tool-result constraints, known overflow patterns.
- `previous_artifact`: optional compact artifact for reuse/update.

The result should include:

- selected items and ordered sections;
- omitted/hidden/forbidden items with reasons;
- compact artifact or fallback artifact;
- recovery refs and exact-read hints;
- token estimates and post-call usage when available;
- validation report;
- cache-stability report;
- trace manifest for eval/debug.

## 4. Module-Specific Strategies

### 4.1 SetupAgent Adapter

SetupAgent should prove the common module against a real workload:

- current-stage long discussion;
- recent raw user wording;
- retained tool outcomes;
- working digest;
- compact summary reuse / update;
- draft-ref recovery hints;
- context report and eval trace.

Setup-specific semantics stay outside the kernel:

- setup stages/steps;
- `SetupWorkspace`;
- setup draft refs;
- setup truth-index refs;
- setup review/commit/readiness;
- setup tool names;
- SkillPack prompt packaging.

Existing setup context services may be migrated, replaced, or retired if they
encode the wrong abstraction.

### 4.2 Story Writer Packet Adapter

Writer packets need high-signal prose generation context:

- accepted story state and branch-visible projections;
- current writing goal;
- recent raw user intent and accepted prose window;
- compact continuity summary;
- selected retrieval cards;
- review overlays when relevant.

Writer packets must not receive raw Core JSON, raw retrieval hit dumps, worker
reasoning, tool traces, usage traces, or hidden future-branch state.

### 4.3 Story Worker Packet Adapter

Worker packets can be broader and more structured than writer packets:

- refs to Core / projection / retrieval / sidecar material;
- diagnostic overlays;
- forbidden-context list;
- source and omission reasons.

Worker context must not leak raw worker reasoning back into prose generation.

### 4.4 Brainstorm Adapter

Brainstorm needs a user-review lifecycle:

- keep an active brainstorm window;
- summarize only the active window plus branch-visible writer snapshot;
- produce editable intent items;
- flush or close the window after summarize / continue-writing.

Brainstorm summary is not Memory OS mutation, Core patch routing, Recall writer,
Archival editor, scheduler, or accepted prose.

### 4.5 Chapter Bridge / Review Adapter

Chapter bridge and review sidecars need continuity:

- chapter goal;
- accepted outline refs;
- transition material;
- unresolved review items;
- compact prior-chapter summary with exact refs.

These sidecars are Runtime Workspace or packet artifacts until another governed
path accepts them. They are not Core, Recall, Archival, or accepted story truth.

### 4.6 Retrieval Composition Adapter

Retrieval should not hand raw hit collections to packet builders. It should
compose deterministic sections with:

- selected candidates;
- budget and ranking decisions;
- exclusion reasons;
- source refs and recovery refs;
- trace manifest.

WritingPacketBuilder should consume composed context, not raw search results.

## 5. Bad Designs To Avoid

- Renaming `SetupContextCompactionService` into a common module and stopping
  there.
- Letting setup stages, draft refs, or tool names become common kernel fields.
- Treating provider-managed state, LangGraph checkpoints, or memory files as RP
  product truth.
- Summarizing away the latest user wording when tone, constraints, or exact
  intent matter.
- Letting compact artifacts mutate Core, Recall, Archival, setup draft, or
  accepted prose without a separate apply path.
- Hiding omissions. A context packet without selected/omitted/hidden evidence is
  hard to debug and impossible to evaluate well.
- Building one generic "old messages summary" rule for all source families.
- Assuming long context eliminates budget policy, cache policy, or recovery refs.

## 6. First Slice Recommendation

The first coherent implementation slice should remain:

```text
Common Context Engineering Kernel + Setup Adapter Pilot
```

Recommended acceptance for that slice:

1. Common contracts exist and are understandable without SetupAgent.
2. Common mechanics cover normalization, deterministic ordering, budget slicing,
   recent raw retention, source fingerprinting, fallback, validation, and trace.
3. Setup adapter maps setup history/digest/tool outcomes/compact summary refs
   into common contracts without exporting setup-specific names into the kernel.
4. Setup path behavior remains externally compatible, but internal setup context
   services are not protected as legacy authority.
5. Tests prove common mechanics and setup adapter behavior.
6. Trellis check is run after the slice before any Story Runtime wiring.

## 7. Working Definition

For RP, Context Engineering should mean:

```text
The common pre-model governance system that constructs the smallest high-signal
model input preserving the runtime's truth boundary, recent intent, recovery
refs, provider constraints, and eval/debug trace.
```

SetupAgent is the proving ground for this definition. It is not the authority.
