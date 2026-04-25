# Assign Session Task

Bind the current AI session to an existing Trellis task, or create a new task and bind it immediately.

---

## Goal

Use this command at the start of a new session when you need to decide:

- keep following the repo default task
- switch this session to an existing task
- create a new task and bind it to this session

This command must prefer **session-scoped assignment** and must not overwrite the repo default unless the user explicitly asks for that.

## Step 1: Inspect Current Resolution

```powershell
python .\.trellis\scripts\task.py current
python .\.trellis\scripts\task.py list --mine
```

If `--mine` returns nothing useful, run:

```powershell
python .\.trellis\scripts\task.py list
```

Summarize for the user:

- current effective task
- whether it came from `session` or `repo`
- the most relevant existing tasks they can choose from

## Step 2: Ask for the Assignment Decision

Ask the user one concise question with these options:

1. keep current repo default
2. bind this session to an existing task
3. create a new task for this session

If they choose an existing task, ask which task name/path to bind.
If they choose a new task, ask for the task title and optional slug.

## Step 3: Execute the Assignment

### Option A: Keep Repo Default

Do not change anything. Confirm the session will continue using the repo default task.

### Option B: Bind Existing Task to This Session

Prefer:

```powershell
python .\.trellis\scripts\task.py start <task> --session
```

If the environment does not expose a session id, use:

```powershell
python .\.trellis\scripts\task.py start <task> --session --session-id <id>
```

### Option C: Create New Task and Bind It to This Session

Prefer:

```powershell
python .\.trellis\scripts\task.py create "<title>" --slug <slug> --start-session
```

If the environment does not expose a session id, use:

```powershell
python .\.trellis\scripts\task.py create "<title>" --slug <slug> --start-session --session-id <id>
```

If the user does not provide a slug, omit `--slug`.

## Step 4: Verify

Always confirm the final resolution:

```powershell
python .\.trellis\scripts\task.py current
```

Report:

- effective task
- source (`session` or `repo`)
- next recommended command: usually `/trellis-continue`

---

## Rules

- Default to `--session`; do not overwrite `.trellis/.current-task` unless the user explicitly asks to change the repo default.
- If no session id is available, say that clearly and either use an explicit `--session-id` or stop and ask the user for it.
- Use Windows PowerShell command examples only.
