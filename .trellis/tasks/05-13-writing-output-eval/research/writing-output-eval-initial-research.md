# Writing Output Eval Initial Research

> Task: `.trellis/tasks/05-13-writing-output-eval`
>
> Date: 2026-05-13

---

## 1. Current RP Runtime Map

The RP writing system is a long-context story runtime, not a standalone prompt.
The current active path is longform-oriented:

```text
StoryGraphRunner
  -> StoryGraphNodes
  -> StoryTurnDomainService
  -> LongformOrchestratorService
  -> LongformSpecialistService
  -> ContextOrchestrationService / WritingPacketBuilder
  -> WritingWorkerExecutionService
  -> persist generated artifact
  -> post-write scheduling / governance
```

Important implementation anchors:

- `backend/rp/graphs/story_graph_runner.py`
  owns the LangGraph shell and turn checkpoints.
- `backend/rp/graphs/story_graph_nodes.py`
  adapts coarse graph nodes such as `orchestrator_plan`, `specialist_analyze`,
  `build_packet`, `writer_run`, `persist_generated_artifact`, and
  `post_write_regression`.
- `backend/rp/services/story_turn_domain_service.py`
  owns command semantics and the runtime-facing generation flow.
- `backend/rp/services/writing_packet_builder.py`
  deterministically builds `WritingPacket` from stable sections and metadata.
- `backend/rp/services/writing_worker_execution_service.py`
  renders the writer prompt and calls the model gateway.
- `backend/rp/eval/*`
  already supports `setup`, `retrieval`, and `activation` eval scopes with
  deterministic assertions, subjective hooks, report artifacts, replay, Ragas
  integration, and Langfuse sync.

Current gap: eval does not yet have a first-class story-writing output scope.
The existing design docs already state that eval should consume runtime trace
and debug surfaces, not become the owner of business logs.

## 2. Why Writing Eval Is Different

Writing output does not have a single reference answer. A good eval case should
therefore define:

- scenario seed and writer packet context;
- user instruction and explicit constraints;
- output-kind expectations;
- deterministic guards;
- rubric dimensions;
- optional baseline candidate for pairwise comparison.

The expected object is not "the exact text"; it is the evaluation contract for
what good text must satisfy.

## 3. Open-Source Projects And Lessons

| Project | Useful for this task | Fit |
| --- | --- | --- |
| DeepEval | GEval-style custom criteria, pytest-like workflow, LLM judge metrics, structured reports. | Strong reference for rubric scoring. Could be adapter later, but existing repo already has subjective hooks. |
| Promptfoo | YAML-driven evals, assertions such as `llm-rubric`, model-graded checks, and practical prompt/model comparison. | Strong reference for prompt iteration and pairwise comparison. Less natural as the core backend runtime dependency. |
| OpenAI Evals | Eval registry, model-graded templates, custom eval patterns. | Useful design reference; less directly product-integrated. |
| Ragas | Aspect critic / rubric-style LLM metrics and retrieval-oriented metrics. | Useful for context-grounded checks; repo already has Ragas runtime integration. |
| Arize Phoenix | Open-source tracing, datasets, experiments, LLM eval helpers. | Useful as observability / experiment backend, not necessary as first core implementation. |
| Unitxt | Reusable benchmark/task/operator library for LLM eval. | Useful if the project later wants a broad benchmark registry; likely too heavy for first slice. |
| Prometheus / Prometheus-Eval | Open evaluator model and rubric-based absolute grading. | Useful if closed judge cost or reproducibility becomes a blocker; not needed for first internal contract. |
| AlpacaEval-style pairwise eval | Win-rate oriented pairwise evaluation. | Useful for DeepSeek-like A/B result aggregation, but its public benchmark is general instruction following rather than long-context fiction. |
| WritingBench / Zhiyin / LitBench / long-form writing benchmarks | Writing-specific benchmark ideas and axis design. | Useful for rubric inspiration and dataset design, not direct drop-in implementation. |

Primary sources checked:

- DeepEval GEval docs: https://deepeval.com/docs/metrics-llm-evals
- Promptfoo model-graded / llm-rubric docs: https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/
- OpenAI Evals repository: https://github.com/openai/evals
- Ragas general-purpose metrics docs: https://docs.ragas.io/en/v0.2.5/concepts/metrics/available_metrics/general_purpose/
- Phoenix experiments docs: https://arize.com/docs/phoenix/datasets-and-experiments/how-to-experiments/run-experiments
- Unitxt LLM-as-judge docs: https://www.unitxt.ai/en/1.15.9/unitxt.llm_as_judge.html
- Prometheus-Eval repository: https://github.com/prometheus-eval/prometheus-eval
- G-Eval paper/code: https://arxiv.org/abs/2303.16634 and https://github.com/nlpyang/geval
- WritingBench paper/repository: https://arxiv.org/abs/2503.05244 and https://github.com/X-PLUG/WritingBench
- Zhiyin Chinese writing benchmark dataset: https://huggingface.co/datasets/zake7749/chinese-writing-benchmark

## 4. Proposed Evaluation Dimensions

Minimum dimensions for RP long-context writing:

1. Instruction following
   - obeys user instruction, output kind, requested edits, and hard constraints.
2. Writing quality
   - fluency, vividness, pacing, scene texture, emotional force, sentence-level
     quality, and absence of filler.
3. Context / canon consistency
   - does not contradict writer packet, core projection, accepted prior text,
     character facts, or known world rules.
4. Style contract adherence
   - follows POV, tense, genre, voice, forbidden style, and user-specified
     writing contract.
5. Continuity and progression
   - advances the scene/chapter coherently without skipping required beats or
     losing thread from recent turns.
6. Format and language compliance
   - Chinese/English requirement, JSON outline schema, no hidden chain-of-
     thought, no exposed retrieval/tool internals.

Pairwise rollups should report win/tie/loss per axis and overall. This mirrors
the DeepSeek paper excerpt more closely than absolute numeric scoring alone.

## 5. Dataset Strategy

Do not start by preparing large fixed-answer datasets. Use layered eval packs:

- smoke cases: deterministic, small, no real provider required;
- rubric cases: one output candidate plus explicit judge rubrics;
- pairwise cases: baseline vs candidate for prompt/model/context comparisons;
- regression cases: previously observed writing failures;
- calibration cases: human-labeled examples used to validate judge behavior.

Each case should preserve enough material for replay: request, story seed,
writer packet summary, output artifact, trace refs, judge prompt version, and
judge response.

## 6. Recommended Implementation Shape

First slice:

```text
backend/rp/eval/models.py
  add story_writing scope and sources

backend/rp/eval/runner.py
  route story_writing cases

backend/rp/eval/graders/judge_registry.py
  add story-writing rubrics

backend/rp/eval/cases/story_writing/...
  add minimal fixture cases

backend/rp/tests/test_eval_story_writing*.py
  lock contracts and report shape
```

Runner mode should support two paths:

1. replay mode: evaluate captured writer packet + output text, stable for unit
   tests and prompt iteration;
2. live mode: seed a story session and run the story graph, useful for real
   provider comparisons.

The first implementation should prioritize replay mode because it gives stable
tests and avoids making judge/model availability a hard dependency.
