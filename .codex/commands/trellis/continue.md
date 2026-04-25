# Continue Current Task

Resume work on the current task and pick up at the right phase/step in `.trellis/workflow.md`.

> Codex note: in this repo, the authoritative executable entrypoint remains the shared skill `trellis-continue` under `.agents/skills/trellis-continue/`. This file is a project-local command mirror for discoverability and consistency.

---

## Step 1: Load Current Context

```powershell
python .\.trellis\scripts\get_context.py
python .\.trellis\scripts\task.py current
```

Confirms: effective current task (`session > repo`), git state, recent commits.

If the session should use a different task, bind it without changing the repo default:

```powershell
python .\.trellis\scripts\task.py start <task> --session --session-id <id>
```

## Step 2: Load the Phase Index

```powershell
python .\.trellis\scripts\get_context.py --mode phase
```

Shows the Phase Index (Plan / Execute / Finish) with routing + skill mapping.

## Step 3: Decide Where You Are

Compare the task's `prd.md` + recent activity against the Phase Index:

- No `prd.md` yet, or requirements unclear → **Phase 1: Plan** (start at step 1.0/1.1)
- `prd.md` exists + context configured, but code not written → **Phase 2: Execute** (step 2.1)
- Code written, pending final quality gate → **Phase 3: Finish** (step 3.1)

Phase rules (full detail in `.trellis/workflow.md`):

1. Run steps **in order** within a phase — `[required]` steps must not be skipped
2. `[once]` steps are already done if the output exists (e.g., `prd.md` for 1.1; `implement.jsonl` with curated entries for 1.3) — skip them
3. You may go back to an earlier phase if discoveries require it

## Step 4: Load the Specific Step

Once you know which step to resume at:

```powershell
python .\.trellis\scripts\get_context.py --mode phase --step <X.X> --platform codex
```

Follow the loaded instructions. After each `[required]` step completes, move to the next.

---

## Reference

Full workflow, skill routing table, and the DO-NOT-skip table live in `.trellis/workflow.md`. This command is only an entry point — the canonical guidance is there.
