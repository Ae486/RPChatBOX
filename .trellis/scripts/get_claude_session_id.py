#!/usr/bin/env python3
r"""
Detect the current Claude Code session id.

Claude Code does not export CLAUDE_SESSION_ID as an environment variable.
This script reconstructs it from the on-disk session log layout:

    ~/.claude/projects/<encoded-project-path>/<session-id>.jsonl
    ~/.claude/projects/<encoded-project-path>/<session-id>/tool-results/...

The "active" session is the one whose tool-results directory (or jsonl
file, as a fallback) has the most recent mtime. This is reliable because
an active session continuously writes tool results and journal entries.

Usage:
    python .\.trellis\scripts\get_claude_session_id.py
    python .\.trellis\scripts\get_claude_session_id.py --project-root H:\chatboxapp
    python .\.trellis\scripts\get_claude_session_id.py --export-ps
    python .\.trellis\scripts\get_claude_session_id.py --export-bash
    python .\.trellis\scripts\get_claude_session_id.py --max-age 600

Exit codes:
    0  Found and printed
    1  Could not detect (no project dir, no sessions, or stale only)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Iterable

SESSION_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                           r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def encode_project_path(project_root: Path) -> str:
    """Encode an absolute path the way Claude Code names project log dirs.

    Claude Code replaces each non `[A-Za-z0-9_.]` character with a single
    `-` (no run-length collapsing). Verified against Windows path
    `H:\\chatboxapp` -> `H--chatboxapp` (two specials -> two dashes).
    """
    abs_path = str(project_root.resolve())
    return re.sub(r"[^A-Za-z0-9_.]", "-", abs_path)


def get_claude_projects_root() -> Path:
    """Return ~/.claude/projects, honoring CLAUDE_HOME if set."""
    claude_home = os.environ.get("CLAUDE_HOME")
    if claude_home:
        return Path(claude_home) / "projects"
    return Path.home() / ".claude" / "projects"


def _candidate_mtime(session_dir: Path, jsonl_file: Path) -> float:
    """Most recent mtime across session subdir contents and the jsonl file.

    The subdir's `tool-results/` is the strongest live-activity signal; jsonl
    mtime is the fallback when the subdir is empty or missing.
    """
    best = 0.0
    if jsonl_file.is_file():
        best = jsonl_file.stat().st_mtime
    if session_dir.is_dir():
        try:
            best = max(best, session_dir.stat().st_mtime)
            tool_results = session_dir / "tool-results"
            if tool_results.is_dir():
                best = max(best, tool_results.stat().st_mtime)
                for entry in tool_results.iterdir():
                    try:
                        best = max(best, entry.stat().st_mtime)
                    except OSError:
                        continue
        except OSError:
            pass
    return best


def _iter_sessions(project_dir: Path) -> Iterable[tuple[str, float]]:
    """Yield (session_id, mtime) pairs for every session under project_dir."""
    seen: set[str] = set()
    for entry in project_dir.iterdir():
        name = entry.name
        sid: str | None = None
        if entry.is_file() and name.endswith(".jsonl"):
            sid = name[: -len(".jsonl")]
        elif entry.is_dir():
            sid = name
        if not sid or not SESSION_ID_RE.match(sid) or sid in seen:
            continue
        seen.add(sid)
        jsonl = project_dir / f"{sid}.jsonl"
        subdir = project_dir / sid
        mtime = _candidate_mtime(subdir, jsonl)
        if mtime > 0:
            yield sid, mtime


def detect_session_id(
    project_root: Path,
    max_age_seconds: float | None = None,
) -> str | None:
    """Return the active Claude Code session id, or None if not found.

    If max_age_seconds is set, sessions older than that threshold are ignored.
    """
    encoded = encode_project_path(project_root)
    project_dir = get_claude_projects_root() / encoded
    if not project_dir.is_dir():
        return None

    candidates = list(_iter_sessions(project_dir))
    if not candidates:
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    sid, mtime = candidates[0]

    if max_age_seconds is not None:
        import time
        if time.time() - mtime > max_age_seconds:
            return None
    return sid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root (default: cwd). Must match the path Claude Code "
             "was launched from.",
    )
    parser.add_argument(
        "--max-age",
        type=float,
        default=None,
        help="Reject sessions whose latest activity is older than this many "
             "seconds. Default: no limit.",
    )
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--export-bash", action="store_true",
                     help="Emit `export CLAUDE_SESSION_ID=<id>` for `eval`.")
    fmt.add_argument("--export-ps", action="store_true",
                     help="Emit `$env:CLAUDE_SESSION_ID = '<id>'` for PowerShell.")
    fmt.add_argument("--export-cmd", action="store_true",
                     help="Emit `set CLAUDE_SESSION_ID=<id>` for cmd.exe.")

    args = parser.parse_args()
    sid = detect_session_id(args.project_root, args.max_age)
    if not sid:
        print(
            f"Error: no active Claude Code session detected for "
            f"{args.project_root.resolve()}",
            file=sys.stderr,
        )
        return 1

    if args.export_bash:
        print(f'export CLAUDE_SESSION_ID="{sid}"')
    elif args.export_ps:
        print(f"$env:CLAUDE_SESSION_ID = '{sid}'")
    elif args.export_cmd:
        print(f"set CLAUDE_SESSION_ID={sid}")
    else:
        print(sid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
