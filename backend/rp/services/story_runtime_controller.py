"""DEPRECATED: moved to rp.services.story.runtime_controller."""
from __future__ import annotations

import warnings

from rp.services.story.runtime_controller import *  # noqa: F401, F403
from rp.services.story.runtime_controller import MemoryBlockHistoryUnsupportedError, StoryRuntimeController  # noqa: F401

warnings.warn(
    "rp.services.story_runtime_controller is deprecated and will be removed next release; "
    "use rp.services.story.runtime_controller instead.",
    DeprecationWarning,
    stacklevel=2,
)
