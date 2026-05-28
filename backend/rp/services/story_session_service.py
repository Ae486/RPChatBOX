"""DEPRECATED: moved to rp.services.story.session_service."""
from __future__ import annotations

import warnings

from rp.services.story.session_service import *  # noqa: F401, F403
from rp.services.story.session_service import StorySessionService  # noqa: F401

warnings.warn(
    "rp.services.story_session_service is deprecated and will be removed next release; "
    "use rp.services.story.session_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
