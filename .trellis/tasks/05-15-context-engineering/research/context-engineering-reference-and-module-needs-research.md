# Context Engineering Reference And Module Needs Research

> Task: `.trellis/tasks/05-15-context-engineering`
>
> Status: research baseline
>
> Date: 2026-05-15

## 1. Position

Context Engineering in RP should be defined as the pre-model context governance layer:

```text
select sources -> normalize source items -> apply visibility / policy / budget ->
retain recent raw windows -> compress or summarize older material ->
validate output -> place sections -> emit trace / usage / read manifest
```

The target is a common foundation consumed by module adapters. SetupAgent is the first proving ground because it has the most concrete current pressure, but it is not the complete architecture, not the authority, and the work must not become a mechanical extraction of existing setup services.

Authority should come from mature context-engineering systems and professional AI-agent engineering references: Claude Code's concrete implementation patterns, pi-mono's explicit pre-LLM context boundary, and technical guidance from OpenAI, Anthropic, Google, and comparable agent platforms. SetupAgent is only a local validation workload. Current setup context code may be optimized, replaced, or deleted when it conflicts with the common module design.

The common module should optimize for this product-level invariant:

```text
Every model call receives the smallest high-signal context packet that preserves
the module's current truth boundary, recovery refs, recent raw intent, and traceability.
```

## 2. Reference Material Survey

### 2.1 Local Claude Code Research

Sources:

- `docs/research/how-claude-code-works-main/docs/03-context-engineering.md`
- `docs/research/how-claude-code-works-main/docs/08-memory-system.md`
- `docs/research/how-claude-code-works-main/docs/09-skills-system.md`

Relevant lessons:

- Each model call is assembled from scratch. Therefore context governance is not "the model remembers"; it is deterministic request construction.
- Stable system prompt, dynamic system context, user/project instructions, message history, tool observations, memory attachments, and skills must be placed deliberately.
- Cache-aware ordering matters. Stable content should be earlier and variable content later; volatile sections need explicit boundaries.
- Message history needs normalization before model calls: role alternation, tool-call/tool-result pairing, hidden virtual messages, unsupported blocks, and API-specific constraints.
- Compression should be progressive: cheap local trimming first, projection or snip views next, LLM summary only when needed, reactive compaction as a last resort.
- Compact output should preserve task continuity and recovery refs, while stripping analysis drafts from the final retained summary.
- Post-compact recovery is a first-class concern. Recently read files, invoked skills, delayed tool metadata, and current plan state may need reinjection.
- Memory works best as an index-plus-lazy-content system: a compact manifest is loaded eagerly, while detailed files are selected and loaded on demand.
- Memory claims are point-in-time observations, not live truth; concrete file/function/path claims need verification before being treated as current.
- Skills demonstrate discovery/execution split: metadata is preloaded for routing, full instruction bodies are lazy-loaded, and forked execution isolates heavy or risky work.

RP implication:

The common Context Engineering kernel must not just trim messages. It needs contracts for section identity, placement, visibility, cache stability, source refs, recovery refs, fallback, and trace.

### 2.2 OpenAI References

Sources:

- OpenAI Conversation State: <https://platform.openai.com/docs/guides/conversation-state?api-mode=responses>
- OpenAI Compaction: <https://developers.openai.com/api/docs/guides/compaction>
- OpenAI Prompt Caching: <https://platform.openai.com/docs/guides/prompt-caching>
- OpenAI Agents SDK Sessions: <https://openai.github.io/openai-agents-python/sessions/>

Relevant lessons:

- Responses API and Conversations API can persist conversation state, but persisted state is not the same as product truth. Applications still need policy over what is allowed into a turn.
- `previous_response_id` reduces manual input handling, but previous input tokens in the chain still count as input billing. Stateful API convenience does not remove the need for budget governance.
- Server-side or standalone compaction reduces context size while preserving state needed for later turns. The returned compaction item is a continuation artifact, not a human-facing canonical record.
- Prompt caching relies on exact prefix matches. Static instructions and examples should be placed before variable request data; tools/images also need to remain identical to benefit from caching.
- Agents SDK sessions separate history persistence from agent runs and can use a compaction session wrapper once a candidate threshold is reached.

RP implication:

The RP common module should own context budget, compaction threshold, compact artifact metadata, and cache-stable placement, but it should not assume provider-managed conversation state equals RP's branch-aware truth or runtime workspace state.

### 2.3 Anthropic References

Sources:

- Anthropic Engineering, Effective Context Engineering for AI Agents: <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>
- Anthropic Prompt Caching: <https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching>
- Anthropic Context Windows: <https://docs.anthropic.com/en/docs/build-with-claude/context-windows>
- Claude Code Memory: <https://docs.anthropic.com/en/docs/claude-code/memory>

Relevant lessons:

- Context engineering is the act of curating the model's limited attention budget, not only writing a good prompt.
- Compaction should be tuned on complex traces. Start with high recall so important facts are not lost, then improve precision to remove noise.
- Tool result and context size management are part of agent quality; token-efficient tool design can matter as much as summary quality.
- Server-side compaction can be a primary long-running conversation strategy, while specialized context editing can clear or reduce specific context classes.
- Prompt caching works best when stable prefix content is separated from varying suffix content and cache breakpoints are placed on stable blocks.
- Claude Code memory uses `MEMORY.md` as a concise index loaded into sessions, with detailed memory files managed separately and editable through `/memory`.

RP implication:

The common module needs both compression quality controls and source-type-specific governance. For example, SetupAgent tool outcomes, Story Runtime recent prose, retrieval cards, and brainstorm discussion windows should not share one generic "old messages summary" rule.

### 2.4 LangChain / LangGraph References

Sources:

- LangChain Context Engineering in Agents: <https://docs.langchain.com/oss/python/langchain/context-engineering>
- LangChain Short-Term Memory: <https://docs.langchain.com/oss/python/langchain/short-term-memory>
- LangChain Context Engineering blog: <https://blog.langchain.com/context-engineering-for-agents/>

Relevant lessons:

- Useful context engineering categories are: write context, select context, compress context, and isolate context.
- Agent context should distinguish runtime context, short-term state, and long-term store.
- Middleware before model calls can trim, summarize, alter prompts, select tools, or change response formats.
- Long-term memory and short-term memory are separate surfaces; thread checkpoints are not a substitute for domain memory truth.
- Isolation is a core pattern: subagents, tools, or specialist contexts can reduce contamination of the main thread.

RP implication:

The RP module should look like pre-model middleware plus typed operation contracts. It should support isolation between writer packets, worker packets, setup turns, brainstorm windows, and review sidecars.

### 2.5 Other Production Reference

Source:

- Manus, Context Engineering for AI Agents: <https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus>

Relevant lessons:

- Keep prompt prefixes stable; even small prefix changes can hurt cache reuse.
- Prefer append-only, deterministic context serialization where possible.
- Masking or filtering may preserve structure better than deleting content when downstream steps depend on stable context shape.
- Irreversible compression is risky because later steps may need details that were not obviously important earlier.
- Externalized memory such as files can be a stronger long-horizon substrate than trying to keep everything in the live window.

RP implication:

The common kernel should preserve stable section ordering and deterministic serialization. When it omits material, the result should carry omitted/hidden refs and reasons so recovery or debug remains possible.

## 3. RP Module Needs

| Module / Consumer | Context Engineering Need | Hard Boundary |
|---|---|---|
| SetupAgent | Stage-local long discussion governance; retain recent raw user intent; compact older setup dialogue; keep working digest, retained tool outcomes, draft recovery refs, usage, and context report. | Setup-specific stage, draft, commit, review, SkillPack, and tool names stay in setup adapter/policy. Current setup context services are migration material, not authority, and may be changed or removed. |
| Story writer packet | Build a narrow writer-facing packet with system sections, core/projection views, recent raw turn/prose window, mode sidecars, retrieval cards, review overlays, and summary sections. | Writer packet must not receive raw authoritative JSON, raw retrieval hit collections, worker reasoning, tool traces, usage traces, or branch/control receipts. |
| Story worker packet | Give governance/analysis workers broader structured refs, sidecar refs, workspace refs, retrieval refs, token budget, and forbidden-context list. | Worker packet is not writer packet; worker context cannot leak back into prose generation as raw reasoning. |
| Writer brainstorm | Maintain an active brainstorm window; summarize only the active window plus branch-visible writer snapshot into editable user intent items; flush window on summarize or continue-writing. | Brainstorm is not Memory OS mutation, Core patch routing, Recall writer, Archival editor, scheduler, or story prose writer. |
| Chapter bridge / review sidecars | Produce compact continuity, chapter goal, accepted outline refs, review overlays, and transition material for the next packet. | Sidecars are packet / Runtime Workspace artifacts until governed later; they are not Core, Recall, Archival, or accepted story truth. |
| Retrieval context composition | Turn retrieval candidates into deterministic selected sections with budget, ranking, exclusion reasons, and trace. | WritingPacketBuilder must consume composed context, not raw retrieval hits. Retrieval owns search/filter/ranking/budget/explanation; story runtime owns intent. |
| Branch-aware memory/read scope | Resolve visible refs before packet build or compact; use branch/turn manifest and as-of object revisions. | Compact must not summarize hidden future memory or latest-session cache state into branch-local packets. |
| Active story internal Block context | Compile Block-backed prompt views for orchestrator and specialist from Core State attachments plus legacy-compatible maps. | It does not replace `WritingPacketBuilder`, and retrieval/Runtime Workspace blocks remain separate in this stage. |
| Future module packets | Reuse common mechanics for source normalization, budget, compact, validation, fallback, trace, and placement. | Module-specific semantics remain adapter-owned. |

## 4. Common Kernel vs Adapter Responsibilities

### Common Kernel Owns

- Source item normalization with stable ids, source family, visibility class, source refs, recovery refs, estimated size, and serialization family.
- Operation request/result contracts for trim-only, compact, summarize, packet-section placement, and trace-only runs.
- Budget and recent-window mechanics.
- Deterministic ordering and serialization.
- Source fingerprinting and summary reuse checks.
- Compact / summary prompt invocation when configured.
- Structured output validation hooks and forbidden-field validation.
- Deterministic fallback summary/report when model output is invalid or unavailable.
- Usage capture, governance metadata, selected/omitted/hidden source reporting, and read-manifest hooks.

### Adapter / Policy Owns

- Which source items enter a request.
- Which refs are visible, hidden, forbidden, or recoverable.
- Which raw windows cannot be compacted away.
- Which schema validates the compact/summarize output.
- Whether failure means fallback, skip section, fail closed, or user-facing error.
- Where the result is placed: setup compact summary, writer packet section, worker sidecar, brainstorm batch, review overlay, or debug-only report.
- Which outputs are allowed to become product truth. The default answer should be "none" unless a separate governed mutation path exists.

## 5. Design Implications For The First Slice

The first coherent slice should be:

```text
Common Context Engineering Kernel + Setup Adapter Pilot
```

Refined deliverables:

1. Define common source item, operation request, budget/window policy, operation result, validation report, fallback report, usage report, and trace metadata contracts.
2. Implement common mechanics that are demonstrably runtime-agnostic: ordering, budget slicing, source fingerprinting, recent-window retention, deterministic fallback, and trace emission.
3. Add setup adapter mapping setup workload needs such as history, working digest, retained tool outcomes, compact summary, and draft-ref policy into common contracts. This adapter may replace current setup internals when needed.
4. Preserve externally required SetupAgent product truth boundaries, not the current internal setup implementation shape.
5. Add tests that prove both the common mechanics and setup adapter behavior.
6. Run Trellis check after the coherent slice, before any Story Runtime wiring.

## 6. Non-Goals / Pitfalls

- Do not call the current SetupAgent context governor "complete".
- Do not treat SetupAgent, `SetupContextGovernorService`, or `SetupContextCompactionService` as authority.
- Do not rename `SetupContextCompactionService` into a common module and stop there.
- Do not preserve setup context services merely because they already exist; optimize, replace, or delete them if the common design requires it.
- Do not let setup stages, draft refs, or setup tool names become kernel primitives.
- Do not wire Story Runtime consumers before the common contract and setup pilot are validated.
- Do not allow compact/summarize output to mutate Core, Recall, Archival, setup drafts, accepted prose, or Runtime Workspace truth without a separate governed apply path.
- Do not treat provider-managed conversation state, LangGraph checkpoints, or memory files as replacements for RP branch-aware read scope and product truth.
- Do not let a summary fully replace recent raw windows where tone, immediate intent, and exact user wording matter.
- Do not lose omitted/hidden source evidence. Debuggability requires knowing what was selected, omitted, hidden, or forbidden and why.

## 7. Working Vocabulary

- **Source item**: A normalized input unit visible to a context operation.
- **Recovery ref**: A stable pointer the runtime can use to re-read exact detail later.
- **Recent raw window**: Source items that must remain uncompressed because exact wording or recency matters.
- **Compact artifact**: A reduced representation used for later model calls; it is not product truth by default.
- **Read manifest**: Deterministic evidence of visible, selected, omitted, hidden, and forbidden refs for a packet or operation.
- **Adapter policy**: Runtime-specific rules that decide source selection, schema, lifecycle, placement, and failure behavior.
