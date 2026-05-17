# Writing Output Eval Methodology

> Task: `.trellis/tasks/05-13-writing-output-eval`
>
> Purpose: define how to evaluate RP long-context writing, what metrics to use,
> and how to build the first test sets.

---

## 1. Core Answer

The evaluation target is not "does the output match a reference answer". The
target is:

```text
Given a story state, writer contract, recent context, retrieval evidence, and
user instruction, did the model produce text that is usable for this story turn?
```

That means each eval case needs three layers:

1. **Hard checks**: deterministic pass/fail constraints.
2. **Rubric scores**: axis-specific LLM or human judgments.
3. **Pairwise preference**: candidate vs baseline win/tie/loss, especially when
   comparing prompts, models, context policies, or retrieval strategies.

Do not begin with a large "golden output" dataset. Begin with compact story
scenarios that define constraints and rubrics. For writing, the "expected" part
of a test case is the evaluation contract, not an exact target paragraph.

## 2. Metric Pyramid

### 2.1 Gate Metrics

Gate metrics answer: should this output be accepted into scoring at all?

| Metric | Type | Example failure |
| --- | --- | --- |
| Language compliance | deterministic | User asked Chinese; output is English. |
| Output-kind compliance | deterministic | Chapter outline expected JSON; output prose. |
| Length band | deterministic | Asked 800-1200 Chinese chars; output 200 chars. |
| Forbidden exposure | deterministic | Output exposes tool calls, retrieval IDs, hidden planning. |
| Required element presence | deterministic | Must include character A and location B; omits B. |
| Schema validity | deterministic | Outline JSON does not parse or misses required fields. |

If a gate fails, the case can still record judge scores, but the report should
mark the output as contract-failed. This prevents beautiful prose from masking
basic product failure.

### 2.2 Axis Scores

Axis scores answer: how good is the text along a meaningful product dimension?

Use 0-5 integer scores plus a short explanation. This is easier for human
calibration than a floating 0-1 score. Convert to pass/warn/fail later:

- 5: excellent, no material issue
- 4: good, minor issue
- 3: usable but clearly flawed
- 2: weak, needs rewrite
- 1: severe failure
- 0: non-answer or unusable

Recommended first axes:

| Axis | What it evaluates | Evidence |
| --- | --- | --- |
| Instruction Following | Whether the output obeys the current user instruction and explicit constraints. | User prompt, command kind, output kind, hard constraints. |
| Context Fidelity | Whether the output is consistent with writer packet context, accepted prior text, core projection, retrieval cards, and known world/character facts. | `WritingPacket`, trace refs, accepted artifacts, retrieval usage. |
| Continuity Progression | Whether it naturally continues the scene/chapter and advances the intended beat without skipping or repeating. | Recent raw turns, chapter phase, accepted segment ids, plan notes. |
| Style Contract Adherence | Whether the text follows POV, tense, genre, tone, prose constraints, and forbidden style rules. | `writer_contract`, setup writing rules, user instruction. |
| Writing Quality | Sentence craft, imagery, pacing, rhythm, specificity, emotional force, and lack of generic filler. | Output text itself plus genre/task context. |
| Character Voice | Whether characters speak/act with distinct, stable, context-appropriate voices. | Character state/projection, recent dialogue, output text. |
| Scene Coherence | Whether spatial, causal, emotional, and temporal logic holds inside the generated segment. | Output text, recent scene state, current beat. |

For the first implementation, use four required axes:

1. Instruction Following
2. Context Fidelity
3. Style Contract Adherence
4. Writing Quality

Continuity, character voice, and scene coherence can be added as specialized
rubrics once the first loop works.

### 2.3 Pairwise Metrics

Pairwise metrics answer: did variant B improve over variant A?

Use this when comparing:

- old prompt vs new prompt;
- model A vs model B;
- context policy A vs context policy B;
- retrieval enabled vs disabled;
- different writer contract wording.

Result shape:

```json
{
  "axis": "writing_quality",
  "winner": "candidate",
  "baseline_score": 3,
  "candidate_score": 4,
  "tie": false,
  "reason": "Candidate has more concrete sensory detail and better pacing."
}
```

Aggregate as:

- per-axis win rate;
- overall win/tie/loss;
- hard-gate failure rate;
- judge confidence / disagreement rate;
- regression tags for repeated failure categories.

DeepSeek-style tables are best modeled as pairwise rollups, not as one absolute
score. Absolute rubric scores explain why; pairwise win rate tells whether an
iteration actually improved.

## 3. Rubric Design

Each rubric must include:

- target axis;
- what the judge should inspect;
- what evidence it may use;
- score scale;
- pass/warn/fail anchors;
- disqualifiers;
- required structured response.

Example rubric skeleton:

```text
Rubric: story_writing/context-fidelity/v1

Task:
Judge whether the output respects the supplied story facts, recent accepted
events, character state, retrieval cards, and writer packet constraints.

Score 5:
No contradiction; uses relevant context naturally; does not overfit or dump
context.

Score 3:
Mostly consistent, but misses one relevant fact, weakly uses context, or creates
minor ambiguity.

Score 1:
Contradicts important canon, invents unsupported facts, or ignores supplied
context.

Disqualifiers:
- Major contradiction with explicit hard fact.
- Exposes internal context/tool/retrieval implementation details.

Return:
status, score, explanation, strengths[], issues[], cited_evidence_refs[].
```

Rubrics should avoid vague words like "good" unless anchored to observable
properties. For example:

- bad: "The writing is vivid."
- better: "The scene contains concrete sensory or action detail that changes
  the reader's understanding of mood, space, character, or conflict."

## 4. Test Set Construction

### 4.1 Start With Eval Packs, Not One Dataset

Use multiple small packs because writing quality has multiple failure modes.

| Pack | Size to start | Purpose |
| --- | ---: | --- |
| Smoke Pack | 5-10 cases | Verify eval plumbing, deterministic gates, report shape. |
| Constraint Pack | 10-20 cases | Catch instruction/style/language/output-kind failures. |
| Context Fidelity Pack | 10-20 cases | Catch canon contradictions and retrieval misuse. |
| Writing Quality Pack | 10-20 cases | Compare prose quality under controlled scenarios. |
| Regression Pack | grows over time | Preserve real failures found during product use. |
| Pairwise Iteration Pack | 20-50 comparisons | Compare prompt/model/context variants. |
| Calibration Pack | 30-100 labeled outputs | Measure whether judge agrees with humans. |

First useful target: 30-50 cases total, not hundreds.

### 4.2 Case Anatomy

Each case should contain:

```json
{
  "case_id": "story_writing.context_fidelity.character_secret.v1",
  "scope": "story_writing",
  "category": "context_fidelity",
  "input": {
    "mode": "replay",
    "story_seed": {},
    "writing_packet": {},
    "user_instruction": "Continue the scene...",
    "candidate_output": "...",
    "baseline_output": "..."
  },
  "expected": {
    "hard_gates": [],
    "rubrics": [],
    "pairwise_axes": []
  },
  "metadata": {
    "difficulty": "medium",
    "failure_mode": "secret_leak",
    "language": "zh",
    "output_kind": "scene_segment"
  }
}
```

For stable tests, begin with replay cases: fixed packet + fixed output. Live
story-turn cases come later.

### 4.3 How To Write Cases

Write cases by failure mode:

1. Pick one risk, not ten.
2. Build the minimum story context needed to expose it.
3. Add one user instruction.
4. Add two candidate outputs if pairwise; otherwise add one candidate output.
5. Define hard gates.
6. Attach 1-3 rubrics.
7. Label expected failure/pass notes for human review.

Good first failure modes:

| Failure mode | Example |
| --- | --- |
| Requirement override | User asks plain modern style; model writes ornate wuxia style. |
| Style drift | Writer contract says third-person limited; output switches to omniscient narration. |
| Canon contradiction | Character known to fear fire suddenly casually lights candles with no transition. |
| Secret leakage | Narration reveals a hidden fact the POV character should not know. |
| Context neglect | Recent scene says rainstorm; output describes noon sunlight. |
| Generic filler | Output uses high-level emotional labels without concrete scene movement. |
| Beat skipping | User asks for hesitation before confession; output jumps directly to confession. |
| Over-context dumping | Output mechanically lists lore instead of dramatizing it. |
| Retrieval misuse | Uses retrieved archival material as confirmed current canon when it was only evidence. |
| Format violation | Asked for outline JSON; returns prose bullets. |

### 4.4 Case Difficulty Ladder

Use three difficulty levels:

- Easy: one explicit requirement, one obvious failure mode.
- Medium: two or three constraints and recent context.
- Hard: conflicting soft preferences, hidden knowledge boundary, or multi-turn
  continuity.

The first dataset should contain mostly easy/medium cases. Hard cases are for
later prompt/model comparison, not for plumbing validation.

## 5. Human Calibration

LLM judges are useful but must be calibrated.

Minimum calibration loop:

1. Create 30 outputs across good/mid/bad quality.
2. Human labels each output on the four required axes with 0-5 scores.
3. Run the judge on the same outputs.
4. Track exact agreement and near agreement, where near agreement means within
   one score point.
5. Inspect disagreements and rewrite rubrics.
6. Freeze rubric version only after it is stable enough.

Practical threshold for first use:

- near-agreement >= 75% on required axes;
- no repeated severe false pass on hard-gate-like failures;
- disagreement examples are stored as calibration cases.

## 6. Report Shape

A useful report should answer these questions:

1. Did the output pass hard gates?
2. Which axes failed?
3. Did the candidate beat the baseline?
4. Was failure due to prompt, context, retrieval, model, or judge uncertainty?
5. Which failure modes are recurring?

Recommended summary fields:

```json
{
  "gate_pass_rate": 0.92,
  "axis_scores": {
    "instruction_following": 4.3,
    "context_fidelity": 3.7,
    "style_contract": 4.1,
    "writing_quality": 3.9
  },
  "pairwise": {
    "overall_win_rate": 0.62,
    "tie_rate": 0.12
  },
  "top_failure_modes": [
    "context_neglect",
    "generic_filler",
    "style_drift"
  ]
}
```

## 7. First Concrete Dataset Plan

Build 12 replay cases first:

| Case group | Count | Main axis |
| --- | ---: | --- |
| Chinese language and style constraints | 2 | Instruction / style |
| POV and knowledge boundary | 2 | Context fidelity |
| Recent-turn continuity | 2 | Continuity |
| Canon contradiction | 2 | Context fidelity |
| Prose quality comparison | 2 | Writing quality |
| Output-kind / format compliance | 2 | Gate metrics |

Each case should include one obviously bad candidate and one acceptable
candidate at first. That makes judge calibration easier. After the pipeline is
stable, add ambiguous cases where the difference is subtle.

## 8. Implementation Implication

The key product artifact is a `StoryWritingEvalCase`, not an eval framework
decision.

Minimal fields:

- story context seed or captured `WritingPacket`;
- candidate output;
- optional baseline output;
- deterministic gate assertions;
- rubric refs;
- human labels, optional but strongly recommended for calibration;
- failure mode tags;
- replay artifacts.

This can be implemented inside the current eval system, but the methodology
above is independent of the implementation framework.
