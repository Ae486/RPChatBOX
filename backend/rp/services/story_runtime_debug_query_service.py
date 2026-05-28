"""DEPRECATED: moved to rp.services.story.runtime_debug_query_service."""
from __future__ import annotations

import warnings

from rp.services.story.runtime_debug_query_service import *  # noqa: F401, F403
from rp.services.story.runtime_debug_query_service import StoryRuntimeDebugQueryServiceError, StoryRuntimeDebugQueryService  # noqa: F401

warnings.warn(
    "rp.services.story_runtime_debug_query_service is deprecated and will be removed next release; "
    "use rp.services.story.runtime_debug_query_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
