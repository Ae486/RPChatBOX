#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex Session Start Hook - Inject Trellis context into Codex sessions.

Output format follows Codex hook protocol:
  stdout JSON → { hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: "..." } }
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import warnings
from io import StringIO
from pathlib import Path

warnings.filterwarnings("ignore")


def should_skip_injection() -> bool:
    return os.environ.get("CODEX_NON_INTERACTIVE") == "1"


def _has_curated_jsonl_entry(jsonl_path: Path) -> bool:
    """Return True iff jsonl has at least one row with a ``file`` field.

    A freshly seeded jsonl only contains a ``{"_example": ...}`` row (no
    ``file`` key) — that is NOT "ready". Readiness requires at least one
    curated entry. Matches the contract used by ``inject-subagent-context.py``.
    """
    try:
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("file"):
                return True
    except (OSError, UnicodeDecodeError):
        return False
    return False


def read_file(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return fallback


def run_script(script_path: Path, session_id: str | None = None) -> str:
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        if session_id:
            env["TRELLIS_SESSION_ID"] = session_id
        cmd = [sys.executable, "-W", "ignore", str(script_path)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            cwd=str(script_path.parent.parent.parent),
            env=env,
        )
        return result.stdout if result.returncode == 0 else "No context available"
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        return "No context available"


def _normalize_task_ref(task_ref: str) -> str:
    normalized = task_ref.strip()
    if not normalized:
        return ""

    path_obj = Path(normalized)
    if path_obj.is_absolute():
        return str(path_obj)

    normalized = normalized.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]

    if normalized.startswith("tasks/"):
        return f".trellis/{normalized}"

    return normalized


def _resolve_task_dir(trellis_dir: Path, task_ref: str) -> Path:
    normalized = _normalize_task_ref(task_ref)
    path_obj = Path(normalized)
    if path_obj.is_absolute():
        return path_obj
    if normalized.startswith(".trellis/"):
        return trellis_dir.parent / path_obj
    return trellis_dir / "tasks" / path_obj


def _sanitize_session_id(session_id: object) -> str:
    if session_id is None:
        return ""
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(session_id).strip())
    return sanitized.strip(".-")[:120]


def _extract_session_id(data: dict) -> str | None:
    for key in (
        "session_id",
        "sessionId",
        "conversation_id",
        "conversationId",
        "thread_id",
        "threadId",
    ):
        value = _sanitize_session_id(data.get(key))
        if value:
            return value

    for container_key in ("session", "conversation", "thread"):
        container = data.get(container_key)
        if isinstance(container, dict):
            value = _sanitize_session_id(container.get("id"))
            if value:
                return value

    for key in ("transcript_path", "transcriptPath", "log_path", "logPath"):
        raw_path = data.get(key)
        if raw_path:
            value = _sanitize_session_id(Path(str(raw_path)).stem)
            if value:
                return value

    for env_key in (
        "TRELLIS_SESSION_ID",
        "CODEX_SESSION_ID",
        "CODEX_THREAD_ID",
        "CLAUDE_SESSION_ID",
        "CURSOR_SESSION_ID",
        "GEMINI_SESSION_ID",
        "QODER_SESSION_ID",
    ):
        value = _sanitize_session_id(os.environ.get(env_key))
        if value:
            return value

    return None


def _read_task_ref_file(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return _normalize_task_ref(path.read_text(encoding="utf-8").strip())
    except OSError:
        return ""


def _get_task_ref(trellis_dir: Path, session_id: str | None) -> tuple[str, str]:
    if session_id:
        session_file = trellis_dir / ".session-tasks" / f"{session_id}.current-task"
        task_ref = _read_task_ref_file(session_file)
        if task_ref:
            return task_ref, "session"

    task_ref = _read_task_ref_file(trellis_dir / ".current-task")
    if task_ref:
        return task_ref, "repo"

    return "", "none"


def _get_task_status(trellis_dir: Path, session_id: str | None = None) -> str:
    task_ref, source = _get_task_ref(trellis_dir, session_id)
    if not task_ref:
        return "Status: NO ACTIVE TASK\nNext: Describe what you want to work on"

    task_dir = _resolve_task_dir(trellis_dir, task_ref)
    if not task_dir.is_dir():
        finish_cmd = "python .\\.trellis\\scripts\\task.py finish --session" if source == "session" else "python .\\.trellis\\scripts\\task.py finish"
        return f"Status: STALE POINTER\nScope: {source}\nTask: {task_ref}\nNext: Task directory not found. Run: {finish_cmd}"

    task_json_path = task_dir / "task.json"
    task_data: dict = {}
    if task_json_path.is_file():
        try:
            task_data = json.loads(task_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, PermissionError):
            pass

    task_title = task_data.get("title", task_ref)
    task_status = task_data.get("status", "unknown")

    if task_status == "completed":
        return f"Status: COMPLETED\nScope: {source}\nTask: {task_title}\nNext: Archive with `python .\\.trellis\\scripts\\task.py archive {task_dir.name}` or start a new task"

    has_context = False
    for jsonl_name in ("implement.jsonl", "check.jsonl", "spec.jsonl"):
        jsonl_path = task_dir / jsonl_name
        if jsonl_path.is_file() and _has_curated_jsonl_entry(jsonl_path):
            has_context = True
            break

    has_prd = (task_dir / "prd.md").is_file()

    if not has_prd:
        return f"Status: NOT READY\nScope: {source}\nTask: {task_title}\nMissing: prd.md not created\nNext: Write PRD (see workflow.md Phase 1.1) then curate implement.jsonl per Phase 1.3"

    if not has_context:
        return f"Status: NOT READY\nScope: {source}\nTask: {task_title}\nMissing: implement.jsonl / check.jsonl missing or empty\nNext: Curate entries per workflow.md Phase 1.3 (spec + research files only), then `task.py start`"

    return f"Status: READY\nScope: {source}\nTask: {task_title}\nNext: Continue with implement or check"


def _extract_range(content: str, start_header: str, end_header: str) -> str:
    """Extract lines starting at `## start_header` up to (but excluding) `## end_header`."""
    lines = content.splitlines()
    start: "int | None" = None
    end: int = len(lines)
    start_match = f"## {start_header}"
    end_match = f"## {end_header}"
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None and stripped == start_match:
            start = i
            continue
        if start is not None and stripped == end_match:
            end = i
            break
    if start is None:
        return ""
    return "\n".join(lines[start:end]).rstrip()


def _build_workflow_toc(workflow_path: Path) -> str:
    """Inject workflow guide: TOC + Phase Index + Phase 1/2/3 step details."""
    content = read_file(workflow_path)
    if not content:
        return "No workflow.md found"

    out_lines = [
        "# Development Workflow — Section Index",
        "Full guide: .trellis/workflow.md  (read on demand)",
        "",
        "## Table of Contents",
    ]
    for line in content.splitlines():
        if line.startswith("## "):
            out_lines.append(line)
    out_lines += ["", "---", ""]

    phases = _extract_range(content, "Phase Index", "Workflow State Breadcrumbs")
    if phases:
        out_lines.append(phases)

    return "\n".join(out_lines).rstrip()


def main() -> None:
    if should_skip_injection():
        sys.exit(0)

    # Read hook input from stdin
    hook_input: dict = {}
    try:
        hook_input = json.loads(sys.stdin.read())
        project_dir = Path(hook_input.get("cwd", ".")).resolve()
    except (json.JSONDecodeError, KeyError):
        project_dir = Path(".").resolve()

    trellis_dir = project_dir / ".trellis"
    session_id = _extract_session_id(hook_input)

    output = StringIO()

    output.write("""<session-context>
You are starting a new session in a Trellis-managed project.
Read and follow all instructions below carefully.
</session-context>

""")

    output.write("<current-state>\n")
    context_script = trellis_dir / "scripts" / "get_context.py"
    output.write(run_script(context_script, session_id=session_id))
    output.write("\n</current-state>\n\n")

    output.write("<workflow>\n")
    output.write(_build_workflow_toc(trellis_dir / "workflow.md"))
    output.write("\n</workflow>\n\n")

    output.write("<guidelines>\n")
    output.write(
        "Project spec indexes are listed by path below. Each index contains a "
        "**Pre-Development Checklist** listing the specific guideline files to "
        "read before coding.\n\n"
        "- If you're spawning an implement/check sub-agent, context is injected "
        "automatically via `{task}/implement.jsonl` / `check.jsonl`. You do NOT "
        "need to read these indexes yourself.\n"
        "- If you're editing code directly in the main session, Read the relevant "
        "index(es) on-demand and follow their Pre-Dev Checklist.\n\n"
    )

    # guides/ inlined (cross-package thinking, broadly useful)
    guides_index = trellis_dir / "spec" / "guides" / "index.md"
    if guides_index.is_file():
        output.write("## guides (inlined — cross-package thinking guides)\n")
        output.write(read_file(guides_index))
        output.write("\n\n")

    # Other indexes — paths only
    paths: list[str] = []
    spec_dir = trellis_dir / "spec"
    if spec_dir.is_dir():
        for sub in sorted(spec_dir.iterdir()):
            if not sub.is_dir() or sub.name.startswith("."):
                continue
            if sub.name == "guides":
                continue
            index_file = sub / "index.md"
            if index_file.is_file():
                paths.append(f".trellis/spec/{sub.name}/index.md")
            else:
                for nested in sorted(sub.iterdir()):
                    if not nested.is_dir():
                        continue
                    nested_index = nested / "index.md"
                    if nested_index.is_file():
                        paths.append(
                            f".trellis/spec/{sub.name}/{nested.name}/index.md"
                        )

    if paths:
        output.write("## Available spec indexes (read on demand)\n")
        for p in paths:
            output.write(f"- {p}\n")
        output.write("\n")

    output.write(
        "Discover more via: "
        "`python .\\.trellis\\scripts\\get_context.py --mode packages`\n"
    )
    output.write("</guidelines>\n\n")

    task_status = _get_task_status(trellis_dir, session_id=session_id)
    output.write(f"<task-status>\n{task_status}\n</task-status>\n\n")

    output.write("""<ready>
Context loaded. Workflow index, project state, and guidelines are already injected above — do NOT re-read them.
Wait for the user's first message, then handle it following the workflow guide.
If there is an active task, ask whether to continue it.
</ready>""")

    context = output.getvalue()
    result = {
        "suppressOutput": True,
        "systemMessage": f"Trellis context injected ({len(context)} chars)",
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        },
    }

    # Codex may run hooks from a Windows console using a non-UTF-8 code page.
    # Escaping non-ASCII keeps stdout JSON valid even when context contains
    # symbols from Trellis docs, without changing the decoded hook payload.
    print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
