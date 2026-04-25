# Finish Work

Wrap up the current session.

> Codex note: in this repo, the authoritative executable entrypoint remains the shared skill `trellis-finish-work` under `.agents/skills/trellis-finish-work/`. This file is a project-local command mirror for discoverability and consistency.

## Step 1: Quality Gate

`trellis-check` should have already run in Phase 3. If not, trigger it now and do not proceed until lint, type-check, tests, and spec compliance pass.

## Step 2: Remind User to Commit

If there are uncommitted changes:

> "Please review the changes and commit when ready."

Do NOT run `git commit` — the human commits after testing.

## Step 3: Record Session (after commit)

Archive finished tasks (judge by work status, not the `status` field):

```powershell
python .\.trellis\scripts\task.py archive <task-name>
```

Append a session entry:

```powershell
python .\.trellis\scripts\add_session.py --title "Title" --summary "Summary"
```

## Step 4: Final Reminder

Confirm:

- task archived if appropriate
- session recorded if appropriate
- specs updated if the work introduced durable new knowledge
