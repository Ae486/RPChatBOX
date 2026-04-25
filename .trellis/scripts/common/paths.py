#!/usr/bin/env python3
"""
Common path utilities for Trellis workflow.

Provides:
    get_repo_root          - Get repository root directory
    get_developer          - Get developer name
    get_workspace_dir      - Get developer workspace directory
    get_tasks_dir          - Get tasks directory
    get_active_journal_file - Get current journal file
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path


# =============================================================================
# Path Constants (change here to rename directories)
# =============================================================================

# Directory names
DIR_WORKFLOW = ".trellis"
DIR_WORKSPACE = "workspace"
DIR_TASKS = "tasks"
DIR_ARCHIVE = "archive"
DIR_SPEC = "spec"
DIR_SCRIPTS = "scripts"
DIR_SESSION_TASKS = ".session-tasks"

# File names
FILE_DEVELOPER = ".developer"
FILE_CURRENT_TASK = ".current-task"
FILE_TASK_JSON = "task.json"
FILE_JOURNAL_PREFIX = "journal-"

SESSION_ID_ENV_VARS = (
    "TRELLIS_SESSION_ID",
    "CODEX_SESSION_ID",
    "CODEX_THREAD_ID",
    "CLAUDE_SESSION_ID",
    "CURSOR_SESSION_ID",
    "GEMINI_SESSION_ID",
    "QODER_SESSION_ID",
)


# =============================================================================
# Repository Root
# =============================================================================

def get_repo_root(start_path: Path | None = None) -> Path:
    """Find the nearest directory containing .trellis/ folder.

    This handles nested git repos correctly (e.g., test project inside another repo).

    Args:
        start_path: Starting directory to search from. Defaults to current directory.

    Returns:
        Path to repository root, or current directory if no .trellis/ found.
    """
    current = (start_path or Path.cwd()).resolve()

    while current != current.parent:
        if (current / DIR_WORKFLOW).is_dir():
            return current
        current = current.parent

    # Fallback to current directory if no .trellis/ found
    return Path.cwd().resolve()


# =============================================================================
# Developer
# =============================================================================

def get_developer(repo_root: Path | None = None) -> str | None:
    """Get developer name from .developer file.

    Args:
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        Developer name or None if not initialized.
    """
    if repo_root is None:
        repo_root = get_repo_root()

    dev_file = repo_root / DIR_WORKFLOW / FILE_DEVELOPER

    if not dev_file.is_file():
        return None

    try:
        content = dev_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("name="):
                return line.split("=", 1)[1].strip()
    except (OSError, IOError):
        pass

    return None


def check_developer(repo_root: Path | None = None) -> bool:
    """Check if developer is initialized.

    Args:
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        True if developer is initialized.
    """
    return get_developer(repo_root) is not None


# =============================================================================
# Tasks Directory
# =============================================================================

def get_tasks_dir(repo_root: Path | None = None) -> Path:
    """Get tasks directory path.

    Args:
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        Path to tasks directory.
    """
    if repo_root is None:
        repo_root = get_repo_root()
    return repo_root / DIR_WORKFLOW / DIR_TASKS


# =============================================================================
# Workspace Directory
# =============================================================================

def get_workspace_dir(repo_root: Path | None = None) -> Path | None:
    """Get developer workspace directory.

    Args:
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        Path to workspace directory or None if developer not set.
    """
    if repo_root is None:
        repo_root = get_repo_root()

    developer = get_developer(repo_root)
    if developer:
        return repo_root / DIR_WORKFLOW / DIR_WORKSPACE / developer
    return None


# =============================================================================
# Journal File
# =============================================================================

def get_active_journal_file(repo_root: Path | None = None) -> Path | None:
    """Get the current active journal file.

    Args:
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        Path to active journal file or None if not found.
    """
    if repo_root is None:
        repo_root = get_repo_root()

    workspace_dir = get_workspace_dir(repo_root)
    if workspace_dir is None or not workspace_dir.is_dir():
        return None

    latest: Path | None = None
    highest = 0

    for f in workspace_dir.glob(f"{FILE_JOURNAL_PREFIX}*.md"):
        if not f.is_file():
            continue

        # Extract number from filename
        name = f.stem  # e.g., "journal-1"
        match = re.search(r"(\d+)$", name)
        if match:
            num = int(match.group(1))
            if num > highest:
                highest = num
                latest = f

    return latest


def count_lines(file_path: Path) -> int:
    """Count lines in a file.

    Args:
        file_path: Path to file.

    Returns:
        Number of lines, or 0 if file doesn't exist.
    """
    if not file_path.is_file():
        return 0

    try:
        return len(file_path.read_text(encoding="utf-8").splitlines())
    except (OSError, IOError):
        return 0


# =============================================================================
# Current Task Management
# =============================================================================

def _get_current_task_file(repo_root: Path | None = None) -> Path:
    """Get .current-task file path.

    Args:
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        Path to .current-task file.
    """
    if repo_root is None:
        repo_root = get_repo_root()
    return repo_root / DIR_WORKFLOW / FILE_CURRENT_TASK


def _get_session_tasks_dir(repo_root: Path | None = None) -> Path:
    """Get the local-only session task pointer directory."""
    if repo_root is None:
        repo_root = get_repo_root()
    return repo_root / DIR_WORKFLOW / DIR_SESSION_TASKS


def sanitize_session_id(session_id: str | None) -> str:
    """Return a filesystem-safe session id, or an empty string if absent."""
    if not session_id:
        return ""
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(session_id).strip())
    sanitized = sanitized.strip(".-")
    return sanitized[:120]


def get_session_id_from_env() -> str | None:
    """Return the first session id exposed through known AI-tool env vars."""
    for key in SESSION_ID_ENV_VARS:
        value = sanitize_session_id(os.environ.get(key))
        if value:
            return value
    return None


def _get_session_task_file(
    session_id: str | None = None,
    repo_root: Path | None = None,
) -> Path | None:
    """Get the session-scoped task pointer file for a session id."""
    sanitized = sanitize_session_id(session_id) or get_session_id_from_env()
    if not sanitized:
        return None
    return _get_session_tasks_dir(repo_root) / f"{sanitized}.current-task"


def normalize_task_ref(task_ref: str) -> str:
    """Normalize a task ref for stable storage in .current-task.

    Stored refs should prefer repo-relative POSIX paths like
    `.trellis/tasks/03-27-my-task`, even on Windows. Absolute paths are preserved
    unless they can later be converted back to repo-relative form by callers.
    """
    normalized = task_ref.strip()
    if not normalized:
        return ""

    path_obj = Path(normalized)
    if path_obj.is_absolute():
        return str(path_obj)

    normalized = normalized.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]

    if normalized.startswith(f"{DIR_TASKS}/"):
        return f"{DIR_WORKFLOW}/{normalized}"

    return normalized


def resolve_task_ref(task_ref: str, repo_root: Path | None = None) -> Path | None:
    """Resolve a task ref from .current-task to an absolute task directory path."""
    if repo_root is None:
        repo_root = get_repo_root()

    normalized = normalize_task_ref(task_ref)
    if not normalized:
        return None

    path_obj = Path(normalized)
    if path_obj.is_absolute():
        return path_obj

    if normalized.startswith(f"{DIR_WORKFLOW}/"):
        return repo_root / path_obj

    return repo_root / DIR_WORKFLOW / DIR_TASKS / path_obj


def _stored_task_ref(task_path: str, repo_root: Path) -> str | None:
    """Validate a task path and convert it to the stable stored ref."""
    normalized = normalize_task_ref(task_path)
    if not normalized:
        return None

    full_path = resolve_task_ref(normalized, repo_root)
    if full_path is None or not full_path.is_dir():
        return None

    try:
        return full_path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(full_path)


def get_current_task(repo_root: Path | None = None) -> str | None:
    """Get current task directory path (relative to repo_root).

    Args:
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        Relative path to current task directory or None.
    """
    current_file = _get_current_task_file(repo_root)

    if not current_file.is_file():
        return None

    try:
        content = current_file.read_text(encoding="utf-8").strip()
        return normalize_task_ref(content) if content else None
    except (OSError, IOError):
        return None


def get_current_task_abs(repo_root: Path | None = None) -> Path | None:
    """Get current task directory absolute path.

    Args:
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        Absolute path to current task directory or None.
    """
    if repo_root is None:
        repo_root = get_repo_root()

    relative = get_current_task(repo_root)
    if relative:
        return resolve_task_ref(relative, repo_root)
    return None


def set_current_task(task_path: str, repo_root: Path | None = None) -> bool:
    """Set current task.

    Args:
        task_path: Task directory path (relative to repo_root).
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        True on success, False on error.
    """
    if repo_root is None:
        repo_root = get_repo_root()

    normalized = _stored_task_ref(task_path, repo_root)
    if not normalized:
        return False

    current_file = _get_current_task_file(repo_root)

    try:
        current_file.write_text(normalized, encoding="utf-8")
        return True
    except (OSError, IOError):
        return False


def clear_current_task(repo_root: Path | None = None) -> bool:
    """Clear current task.

    Args:
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        True on success.
    """
    current_file = _get_current_task_file(repo_root)

    try:
        if current_file.is_file():
            current_file.unlink()
        return True
    except (OSError, IOError):
        return False


def get_session_current_task(
    session_id: str | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Get the current task for one AI session, if set."""
    session_file = _get_session_task_file(session_id, repo_root)
    if session_file is None or not session_file.is_file():
        return None

    try:
        content = session_file.read_text(encoding="utf-8").strip()
        return normalize_task_ref(content) if content else None
    except (OSError, IOError):
        return None


def set_session_current_task(
    task_path: str,
    session_id: str | None = None,
    repo_root: Path | None = None,
) -> bool:
    """Set the current task for one AI session without touching repo default."""
    if repo_root is None:
        repo_root = get_repo_root()

    session_file = _get_session_task_file(session_id, repo_root)
    if session_file is None:
        return False

    normalized = _stored_task_ref(task_path, repo_root)
    if not normalized:
        return False

    try:
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(normalized, encoding="utf-8")
        return True
    except (OSError, IOError):
        return False


def clear_session_current_task(
    session_id: str | None = None,
    repo_root: Path | None = None,
) -> bool:
    """Clear the session-scoped task pointer for one AI session."""
    session_file = _get_session_task_file(session_id, repo_root)
    if session_file is None:
        return False

    try:
        if session_file.is_file():
            session_file.unlink()
        return True
    except (OSError, IOError):
        return False


def get_effective_current_task(
    session_id: str | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Return session task if set, otherwise the repository default task."""
    session_task = get_session_current_task(session_id, repo_root)
    return session_task or get_current_task(repo_root)


def get_current_task_with_source(
    session_id: str | None = None,
    repo_root: Path | None = None,
) -> tuple[str | None, str]:
    """Return the effective current task and whether it came from session/repo."""
    session_task = get_session_current_task(session_id, repo_root)
    if session_task:
        return session_task, "session"

    repo_task = get_current_task(repo_root)
    if repo_task:
        return repo_task, "repo"

    return None, "none"


def clear_session_task_refs_for_task(
    task_path: str,
    repo_root: Path | None = None,
) -> int:
    """Remove local session pointers that reference a task being archived."""
    if repo_root is None:
        repo_root = get_repo_root()

    normalized = normalize_task_ref(task_path)
    if not normalized:
        return 0

    session_dir = _get_session_tasks_dir(repo_root)
    if not session_dir.is_dir():
        return 0

    cleared = 0
    for session_file in session_dir.glob("*.current-task"):
        try:
            content = normalize_task_ref(session_file.read_text(encoding="utf-8").strip())
        except (OSError, IOError):
            continue
        if content == normalized or content.endswith(f"/{Path(normalized).name}"):
            try:
                session_file.unlink()
                cleared += 1
            except (OSError, IOError):
                pass
    return cleared


def has_current_task(repo_root: Path | None = None) -> bool:
    """Check if has current task.

    Args:
        repo_root: Repository root path. Defaults to auto-detected.

    Returns:
        True if current task is set.
    """
    return get_current_task(repo_root) is not None


# =============================================================================
# Task ID Generation
# =============================================================================

def generate_task_date_prefix() -> str:
    """Generate task ID based on date (MM-DD format).

    Returns:
        Date prefix string (e.g., "01-21").
    """
    return datetime.now().strftime("%m-%d")


# =============================================================================
# Monorepo / Package Paths
# =============================================================================


def get_spec_dir(package: str | None = None, repo_root: Path | None = None) -> Path:
    """Get the spec directory path.

    Single-repo: .trellis/spec
    Monorepo with package: .trellis/spec/<package>

    Uses lazy import to avoid circular dependency with config.py.
    """
    if repo_root is None:
        repo_root = get_repo_root()

    from .config import get_spec_base

    base = get_spec_base(package, repo_root)
    return repo_root / DIR_WORKFLOW / base


def get_package_path(package: str, repo_root: Path | None = None) -> Path | None:
    """Get a package's source directory absolute path from config.

    Returns:
        Absolute path to the package directory, or None if not found.
    """
    if repo_root is None:
        repo_root = get_repo_root()

    from .config import get_packages

    packages = get_packages(repo_root)
    if not packages or package not in packages:
        return None

    info = packages[package]
    if isinstance(info, dict):
        rel_path = info.get("path", package)
    else:
        rel_path = str(info)

    return repo_root / rel_path


# =============================================================================
# Main Entry (for testing)
# =============================================================================

if __name__ == "__main__":
    repo = get_repo_root()
    print(f"Repository root: {repo}")
    print(f"Developer: {get_developer(repo)}")
    print(f"Tasks dir: {get_tasks_dir(repo)}")
    print(f"Workspace dir: {get_workspace_dir(repo)}")
    print(f"Journal file: {get_active_journal_file(repo)}")
    print(f"Current task: {get_current_task(repo)}")
