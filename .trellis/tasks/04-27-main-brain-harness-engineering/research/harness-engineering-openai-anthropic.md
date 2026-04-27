# Harness Engineering Research

Date: 2026-04-27

## Question

What does `harness engineering` mean in current agent engineering practice, and how do OpenAI and Anthropic frame it?

## Short Answer

`Harness engineering` is the engineering of the environment around the model so the model can act reliably as an agent.

It is not only prompt writing.

It usually includes:

- the loop that drives model calls
- tool orchestration
- context shaping and handoff
- state persistence and recovery
- sandbox or execution environment boundaries
- observability and eval integration
- mechanical quality constraints around the repo or workflow

OpenAI currently uses `harness engineering` in a fairly broad, product-engineering sense.

Anthropic more often uses `harness design` or `agent harness` and speaks about it as the scaffold around the model, especially for long-running work and evals.

## OpenAI

### Source 1: Harness engineering: leveraging Codex in an agent-first world

OpenAI uses the term very explicitly here.

Key framing:

- humans steer, agents execute
- the engineer's role shifts from writing code to designing environments, specifying intent, and building feedback loops
- repository knowledge should be the system of record
- `AGENTS.md` should be a map, not a giant encyclopedia
- plans should be first-class, versioned artifacts
- architecture and "taste" should be enforced mechanically
- recurring cleanup / garbage collection is part of the harness

Important implications:

1. Harness engineering includes repo structure and knowledge layout, not just runtime loop code.
2. Agent legibility is treated as a primary design goal.
3. Feedback loops and enforcement matter as much as the base model.

Supporting excerpts:

- OpenAI says the team needed to "design environments, specify intent, and build feedback loops" so agents could work reliably.
- OpenAI also says plans are "first-class artifacts" and that this enables progressive disclosure.
- OpenAI says knowledge-base structure is enforced mechanically with linters and CI.

### Source 2: The next evolution of the Agents SDK

This post is more runtime/product oriented.

Key framing:

- the Agents SDK provides a more capable harness for the agent loop
- the harness now includes configurable memory, sandbox-aware orchestration, filesystem tools, MCP, skills, AGENTS.md, shell, and apply-patch-style editing
- the harness should align execution with the model's natural operating pattern

Important implications:

1. OpenAI treats harness as standardized agent infrastructure, not only custom app glue.
2. Runtime primitives such as memory, tools, skills, and sandboxing are harness concerns.
3. A good harness helps unlock more model capability by reducing mismatch between the model and execution environment.

### OpenAI summary

OpenAI's use of `harness engineering` is broad:

- repo-as-context architecture
- instructions and knowledge organization
- mechanical enforcement
- runtime loop and tool stack
- maintenance loops that keep an agent-generated codebase legible over time

In short: OpenAI treats harness engineering as the full operating system around the agent.

## Anthropic

### Source 1: Demystifying evals for AI agents

Anthropic gives a crisp definition:

- an evaluation harness runs evals end-to-end
- an agent harness (or scaffold) enables a model to act as an agent by processing inputs, orchestrating tool calls, and returning results

Important implications:

1. Anthropic sharply distinguishes `agent harness` from `evaluation harness`.
2. When evaluating an agent, you are evaluating the model plus harness together.
3. Poor eval results can come from harness constraints, not only model weakness.

This is a very useful vocabulary distinction for architecture work.

### Source 2: Harness design for long-running application development

Anthropic treats harness design as a major performance lever.

Key framing:

- harness design is key for frontier agentic coding
- structured decomposition and structured handoff artifacts materially improve long-running work
- context resets can outperform compaction for some long tasks
- harness components should be stress-tested because each one encodes an assumption about model weakness
- those assumptions can become stale as models improve

Important implications:

1. Harness complexity should be justified, not romanticized.
2. Handoff artifacts are part of harness design.
3. Long-running agent performance depends heavily on context strategy and orchestration strategy.

### Source 3: Scaling Managed Agents: Decoupling the brain from the hands

Anthropic pushes the abstraction further.

Key framing:

- session, harness, and sandbox should be separable interfaces
- the harness is the loop that calls Claude and routes tool calls
- the harness should not be over-coupled to a single container or execution environment
- durability, recovery, security, and scale improve when the "brain" is decoupled from the "hands"

Important implications:

1. Harness is an orchestration interface layer.
2. Durable event logs and resumability are harness-adjacent responsibilities.
3. Security boundaries are part of harness design, not an afterthought.

### Anthropic summary

Anthropic's framing is more architecturally precise:

- harness = scaffold / orchestration loop around the model
- eval harness is separate from agent harness
- long-running work needs careful handoff, reset, and recovery design
- good harnesses are modular and should evolve as models improve

## Cross-Company Synthesis

Common ground:

- the model alone is not the agent
- the surrounding loop and environment materially affect outcomes
- tools, context, and feedback loops are central
- observability and eval are necessary once systems scale
- assumptions encoded into the harness must be revisited over time

Main difference in emphasis:

- OpenAI emphasizes agent legibility, repo structure, mechanical enforcement, and agent-first engineering workflow
- Anthropic emphasizes scaffold boundaries, long-running orchestration, recovery, context resets, and eval clarity

## Useful Vocabulary

### Agent harness

The runtime scaffold that lets a model behave like an agent.

Typical contents:

- loop
- tool routing
- context construction
- state / handoff
- retries / recovery
- sandbox / execution interface

### Evaluation harness

The infrastructure that runs agent evals end-to-end.

Typical contents:

- task runner
- dataset loading
- environment setup
- trace capture
- grading
- aggregation / reporting

### Harness engineering

The discipline of designing and maintaining the harness so that agents perform reliably, recover cleanly, stay aligned with real constraints, and remain legible to future runs and future engineers.

## Relevance To H:/chatboxapp

For this repository, the concept is directly relevant in at least five places:

1. `setup agent runtime`
   - loop design
   - tool orchestration
   - completion guard
   - reflection / recovery
   - step-to-step handoff

2. `eval`
   - Langfuse traces
   - offline replay / compare
   - attribution logic
   - retrieval-specific scoring layers

3. `tools`
   - setup private tools
   - retrieval entry points
   - tool metadata and error semantics

4. `skills / prompt resources`
   - mode knowledge packaging
   - progressive disclosure
   - avoiding prompt-blob collapse

5. `main brain`
   - task decomposition
   - repo-local knowledge as source of truth
   - architectural boundary enforcement
   - session handoff quality

## Main-Brain Interpretation

For a "main brain" session in this repo, `harness engineering` should be understood as:

- designing the operating environment around RP agents
- not only deciding prompts, but deciding the execution contract
- keeping setup / runtime / eval / retrieval / tools / documentation aligned
- making the system diagnosable when it fails
- making future sessions legible through structured artifacts

That means the "main brain" should care about:

- what state is carried
- what state is compressed
- what is retrieved on demand
- what tools are exposed
- how failures are classified
- how traces are captured
- what artifacts become the next session's source of truth

## Sources

1. OpenAI, "Harness engineering: leveraging Codex in an agent-first world"
   - https://openai.com/index/harness-engineering/

2. OpenAI, "The next evolution of the Agents SDK"
   - https://openai.com/index/the-next-evolution-of-the-agents-sdk/

3. OpenAI API docs, "Evaluate agent workflows"
   - https://developers.openai.com/api/docs/guides/agent-evals

4. Anthropic, "Demystifying evals for AI agents"
   - https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

5. Anthropic, "Harness design for long-running application development"
   - https://www.anthropic.com/engineering/harness-design-long-running-apps

6. Anthropic, "Scaling Managed Agents: Decoupling the brain from the hands"
   - https://www.anthropic.com/engineering/managed-agents
