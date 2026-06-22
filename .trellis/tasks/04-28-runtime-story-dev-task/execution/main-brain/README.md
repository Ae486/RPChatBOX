# Main Brain Control Room

Status: active working notes
Task: `.trellis/tasks/04-28-runtime-story-dev-task`
Created: 2026-06-23

This folder is the control room for the main-brain session. It records the rules,
standing decisions, and development direction that future agents must follow
while planning and coordinating story runtime work.

These notes are proposal/control documents, not final specs. When a point
becomes a frozen implementation contract, move it into the relevant
`execution/phase-*` document or `research/modules/*` document.

## Files

- `operating-rules.md` — rules the main-brain session and delegated agents must
  follow.
- `development-direction.md` — current development direction for the agent
  framework, harness, S3, and old MVP chain.
- `harness-gap-and-completion-plan.md` — current gap between the landed harness
  substrate and the desired runtime-agent framework, plus completion gates.
- `decision-queue.md` — user decisions needed before PRD / implementation
  planning can be treated as settled.
- `implementation-leadership-rules.md` — mandatory leadership rules for
  autonomous implementation, assistant/reviewer coordination, fresh review,
  glue coding, YCE-only search, and testing strategy.

## Relationship To Existing Execution Docs

- `../00-INDEX.md` remains the execution journal index.
- `../decision-log.md` remains the append-only ADR log for phase decisions.
- `../HANDOFF.md` remains the detailed handoff for prior W5-A execution state.
- `../audits/runtime-story-agent-framework-harness-s3-review.md` records the
  current existing-implementation review that triggered this control-room layer.

## Update Rule

Update this folder whenever the user makes a planning decision that affects:

- old MVP chain handling;
- story agent / harness direction;
- S3 memory/proposal/apply scope;
- tool design boundaries;
- subagent dispatch and verification policy;
- autonomous implementation and review/gate policy;
- future S4/S5/S6/S7 planning assumptions.
