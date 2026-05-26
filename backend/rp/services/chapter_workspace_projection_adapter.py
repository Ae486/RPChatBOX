"""DEPRECATED: moved to rp.services.projection.chapter_workspace_adapter."""
from __future__ import annotations

import warnings

from rp.services.projection.chapter_workspace_adapter import *  # noqa: F401, F403
from rp.services.projection.chapter_workspace_adapter import (  # noqa: F401
    ChapterWorkspaceProjectionAdapter,
)

warnings.warn(
    "rp.services.chapter_workspace_projection_adapter is deprecated and will be "
    "removed next release; use rp.services.projection.chapter_workspace_adapter instead.",
    DeprecationWarning,
    stacklevel=2,
)
