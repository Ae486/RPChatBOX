"""DEPRECATED: moved to rp.services.story.runtime_workspace_facade."""
from __future__ import annotations

import warnings

from rp.services.story.runtime_workspace_facade import *  # noqa: F401, F403
from rp.services.story.runtime_workspace_facade import WriterPacketSurfaceRefs, WorkerExecutionSurfaceRefs, WriterOutputSurfaceRefs, StoryRuntimeWorkspaceFacade  # noqa: F401

warnings.warn(
    "rp.services.story_runtime_workspace_facade is deprecated and will be removed next release; "
    "use rp.services.story.runtime_workspace_facade instead.",
    DeprecationWarning,
    stacklevel=2,
)
