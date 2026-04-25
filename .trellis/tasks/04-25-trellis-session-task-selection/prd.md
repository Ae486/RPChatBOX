# Trellis session task selection

## Goal

Allow parallel AI sessions in the same repository to choose different Trellis tasks without overwriting the repository-level default task pointer.

## Requirements

* Preserve `.trellis/.current-task` as the repository default for backwards compatibility.
* Add a session-scoped task pointer that can override the repository default when a session identifier is available.
* Add task CLI commands for selecting, clearing, and inspecting the session-scoped task.
* Add user-facing command/skill entrypoints so a new session can choose an existing task, keep the repo default, or create-and-bind a new task without manually reconstructing the flow.
* Mirror the Trellis command entrypoints into `.codex/commands/trellis/` for Codex-local discoverability, while keeping `.agents/skills/trellis-*` as the current authoritative Codex integration path.
* Update Codex hooks so workflow state, session start context, and statusline prefer the session task over the repository default.
* Keep behavior safe when no session identifier is available: fall back to repository default and clearly report the limitation.
* Keep PowerShell examples Windows-friendly.
* In Codex, treat `CODEX_THREAD_ID` as a valid current-session identifier so session binding can complete without manual id copy/paste when the environment already exposes it.

## Acceptance Criteria

* [x] `task.py start <task>` keeps working as the repository-level default.
* [x] A session-level command can bind a task without changing `.trellis/.current-task`.
* [x] Hook-generated workflow state uses `session task > repo task > no task`.
* [x] Existing no-task and stale-pointer behavior remains understandable.
* [x] The implementation is covered by script-level smoke checks.
* [x] Cursor / Claude / Codex each have a session-assignment entrypoint aligned with their local Trellis integration style.
* [x] Codex now has mirrored Trellis command docs in `.codex/commands/trellis/` for `continue`, `finish-work`, and `assign-task`.
* [x] Codex can now use `CODEX_THREAD_ID` as the implicit session id for `task.py ... --session`.

## Out of Scope

* Upstream Trellis package/template publication.
* Non-Codex platforms beyond keeping mirrored hook scripts structurally aligned where local copies exist.
* Changing existing task metadata schema.

## Technical Notes

* Existing problem: `.trellis/.current-task` is repo-scoped, so parallel sessions overwrite each other.
* Desired storage: repo default remains `.trellis/.current-task`; session overrides live outside the shared default pointer.
* Current project has multiple unrelated worktree changes; this task only modifies Trellis/Codex hook and workflow files.
