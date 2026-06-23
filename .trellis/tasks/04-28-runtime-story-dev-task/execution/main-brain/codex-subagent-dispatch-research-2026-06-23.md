# Codex Subagent Dispatch Research And Test

Status: active operational note
Date: 2026-06-23
Task: `04-28-runtime-story-dev-task`

## Question

How should the main-brain dispatch Codex subagents for S3 and later runtime
implementation/check work?

## Sources Checked

Official OpenAI / Codex sources:

- `https://developers.openai.com/codex/subagents`
- `https://developers.openai.com/codex/concepts/subagents`
- `https://developers.openai.com/codex/noninteractive`
- `https://developers.openai.com/codex/cli/reference`
- Fresh local Codex manual fetched by `openai-docs` helper:
  `C:\Users\55473\AppData\Local\Temp\openai-docs-cache\codex-manual.md`

Relevant official points:

- Codex subagent workflows spawn specialized agents in parallel and collect the
  results in one parent response.
- Codex does not spawn subagents automatically. The parent must explicitly ask
  for subagents or parallel agent work.
- Subagent activity is surfaced in Codex app and CLI. The CLI can inspect active
  agent threads with `/agent` in interactive sessions.
- Custom agents are defined as standalone TOML files under `.codex/agents/` or
  `~/.codex/agents/`, with required `name`, `description`, and
  `developer_instructions`.
- Subagents inherit the parent sandbox and approval policy. In non-interactive
  flows, actions that need fresh approval fail and surface the error to the
  parent.
- `codex exec` is the official non-interactive CLI entry for scripted /
  automation-style Codex runs. It supports `--sandbox`, `--cd`,
  `--output-last-message`, `--json`, and `resume`.

## Local Test Results

### Test 1: nested `codex exec` inside a read-only Codex run

Command shape:

```text
codex exec --cd H:\chatboxapp --sandbox read-only --json "spawn one read-only explorer subagent..."
```

Observed behavior:

- The parent run did not expose a built-in spawn/subagent tool.
- It attempted to shell out to `codex exec` from inside the read-only run.
- The nested CLI failed with:
  `failed to initialize in-process app-server client: 拒绝访问。 (os error 5)`.
- This also produced `.codex/tmp/arg0` permission warnings.

Conclusion:

- Do not nest `codex exec` inside a Codex subagent/sandbox as the standard
  dispatch mechanism.

### Test 2: direct main-brain `codex exec` no-op child session

Command:

```text
codex exec --ephemeral --sandbox read-only --ignore-rules --skip-git-repo-check -C "C:\Users\55473\AppData\Local\Temp" -o "C:\Users\55473\AppData\Local\Temp\codex-direct-dispatch-test.md" "No-op dispatch test..."
```

Result:

```text
DIRECT_CODEX_EXEC_OK
session id: 019ef217-9dfd-7351-b6db-efbb0e3de765
model: gpt-5.5
sandbox: read-only
approval: never
```

Conclusion:

- Direct `codex exec` from the main-brain session works as an official
  Codex-native non-interactive child session.

### Test 3: direct `codex exec` asking for built-in internal spawn

Command shape:

```text
codex exec --ephemeral --sandbox read-only --ignore-rules --skip-git-repo-check -C "%TEMP%" --json "Use Codex's built-in subagent workflow if it is exposed..."
```

Result:

```text
spawned=false; result=no built-in subagent/spawn tool is exposed in this run
```

Conclusion:

- In this current non-interactive CLI environment, internal subagent spawn tools
  are not exposed to the child session.
- If an interactive Codex CLI/app session exposes `/agent` and internal spawn,
  that path should be preferred for true subagent workflows.
- For this main-brain API session, the practical verified path is direct
  `codex exec` child-session dispatch.

## Operational Rule

Use this priority order:

1. Prefer true Codex internal subagent workflow when the current parent session
   exposes it, especially for parallel read-only reviews.
2. In this API/main-brain environment, use direct `codex exec` from the
   main-brain process as the verified Codex-native child-session dispatch path.
3. Do not ask a child Codex session to launch another `codex exec` unless an
   isolated writable `CODEX_HOME` / temp setup has been deliberately prepared.
4. For review/check child sessions, use `--sandbox read-only`, pre-feed source
   docs, pre-feed test results, and forbid pytest unless explicitly required.
5. For implementation child sessions, use a narrow prompt, explicit in-scope
   files, no git mutation, and leader-owned verification/commit.
6. Record the command, session id when available, and output path in the slice
   worklog or gate record.

## S3 Immediate Application

For S3g-b fresh review, use direct `codex exec` from the main-brain session with
the existing review brief as input. This is not the same as the internal
parallel subagent workflow documented by OpenAI, but it is the verified
Codex-native non-interactive child-session fallback available in this
environment.
