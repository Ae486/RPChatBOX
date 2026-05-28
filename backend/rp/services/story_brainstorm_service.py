"""DEPRECATED: moved to rp.services.story.brainstorm_service."""
from __future__ import annotations

import warnings

from rp.services.story.brainstorm_service import *  # noqa: F401, F403
from rp.services.story.brainstorm_service import StoryBrainstormServiceError, StoryBrainstormService  # noqa: F401

warnings.warn(
    "rp.services.story_brainstorm_service is deprecated and will be removed next release; "
    "use rp.services.story.brainstorm_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
