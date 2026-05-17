# Writing Output Eval PRD

> Task: `.trellis/tasks/05-13-writing-output-eval`
>
> Status: planning / research
>
> Goal: build an evaluation system for RP long-context AI writing output.

---

## 1. Problem

RP long-context writing quality is shaped by model choice, system prompt,
writer contract, context assembly, retrieval, worker hints, and post-write
governance. Unlike coding tasks, a generated story segment usually has no
single deterministic expected answer. This makes prompt and context iteration
hard: the team needs repeatable evidence for whether a change improves
instruction following, style, continuity, and writing quality.

The DeepSeek writing evaluation excerpt shows the product-shaped target:
pairwise comparison, win / tie / loss, and separate axes such as instruction
following and writing quality. The paper excerpt does not expose enough
implementation detail for direct reuse, but it confirms the evaluation shape is
reasonable: writing quality can be evaluated with explicit rubrics and pairwise
judgment.

## 2. Scope

This task should extend the existing RP eval system toward `story_writing`
without letting eval own business runtime logs.

In scope:

- understand current RP long-context writing flow and trace surfaces;
- define writing-output eval dimensions and case shape;
- reuse the existing eval runner / subjective hook / rubric registry where
  practical;
- support both absolute rubric scoring and pairwise baseline comparison;
- support seeded story scenarios where the expected answer is a rubric and
  constraints, not a fixed reference text;
- produce structured reports that can compare prompt / context / model variants.

Out of scope for the first slice:

- replacing the story runtime;
- replacing retrieval, memory, or post-write governance;
- adding a large external eval platform as the core dependency;
- building full UI dashboards before the backend eval contract is stable;
- treating LLM judge output as ground truth without deterministic guards or
  human calibration.

## 3. Product Requirements

1. The system must evaluate generated writing from the same data path used by
   story runtime: request, writer packet, output artifact, runtime trace, and
   post-write status.
2. The first-class dimensions must include:
   - instruction following;
   - writing quality;
   - context / canon consistency;
   - style and writer-contract adherence;
   - continuity across turns;
   - format / language / output-kind compliance.
3. Deterministic assertions must run before LLM judging where possible:
   language, length band, forbidden terms, required names, JSON schema, output
   kind, and trace existence.
4. LLM judging must use explicit rubric refs and structured output, not freeform
   commentary only.
5. Pairwise comparison must be supported for baseline prompts / models:
   candidate A wins, candidate B wins, tie, with axis-specific reasons.
6. Eval must consume runtime trace / artifacts; it must not become the owner of
   runtime trace.
7. Reports must make iteration decisions visible: which prompt / model /
   context policy won, where it failed, and whether failures are deterministic,
   judge-assessed, or infrastructure-related.

## 3.1 Evaluation Methodology

The core methodology is documented in
`research/writing-output-eval-methodology.md`.

The short version:

- first run deterministic gate checks such as language, length band, output
  kind, schema validity, forbidden internal-detail exposure, and required
  element presence;
- then score axis rubrics, starting with instruction following, context
  fidelity, style contract adherence, and writing quality;
- then use pairwise comparison for prompt/model/context iteration, reporting
  candidate-vs-baseline win/tie/loss per axis and overall;
- build test sets by failure mode, not by fixed reference answers.

For writing, the expected object is not a single golden paragraph. The expected
object is the case's constraints, rubrics, gates, and optionally human labels
used to calibrate the judge.

## 4. Technical Direction

The recommended first implementation is internal-first:

```text
EvalCase(scope="story_writing")
  -> seed or load story runtime state
  -> run one story turn or replay captured writer output
  -> collect writer packet / output artifact / trace refs
  -> deterministic assertions
  -> rubric judge hooks
  -> optional pairwise judge
  -> report + replay artifacts
```

This should reuse the existing `backend/rp/eval` structure:

- extend `EvalScope` with `story_writing`;
- add story-writing sources such as `story_turn_result`, `writing_packet`,
  `writer_output`, `post_write_trigger`, and `runtime_materials`;
- add rubric refs under `backend/rp/eval/graders/judge_registry.py`;
- add runner support that uses the existing story runtime factory path;
- add fixtures that create compact but realistic longform story sessions.

External open-source frameworks should be treated as references or optional
adapters after the internal contract stabilizes. DeepEval and Promptfoo are the
most relevant for rubric and pairwise judge patterns; Ragas is most useful for
retrieval/context-grounded aspects and is already partially represented in the
repo.

## 5. First Implementation Slice

The first coherent slice should be backend-only:

1. Add `story_writing` eval scope contracts.
2. Add 3-5 rubric specs:
   - `story_writing/instruction-following/v1`
   - `story_writing/writing-quality/v1`
   - `story_writing/context-consistency/v1`
   - `story_writing/style-contract/v1`
   - optional `story_writing/pairwise-overall/v1`
3. Add one deterministic fixture case that can run without real provider calls.
4. Add one subjective-hook case that materializes judge artifacts when judge is
   disabled, and can run real judging when enabled.
5. Add focused tests for case loading, runner routing, rubric lookup, and report
   artifact shape.

## 6. Open Questions

- Should first story-writing eval execute a full story turn, or start from
  captured writer packet + output replay for stability?
- Which model should be the default judge in real-provider runs?
- Should pairwise comparison be implemented in the existing subjective hook
  model, or as a separate comparison module next to `comparison.py`?
- What minimum human-labeled calibration set is acceptable before using judge
  scores to guide prompt changes?
