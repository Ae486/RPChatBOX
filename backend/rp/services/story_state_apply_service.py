"""DEPRECATED: moved to rp.services.story.state_apply_service."""
from __future__ import annotations

import warnings

from rp.services.story.state_apply_service import *  # noqa: F401, F403
from rp.services.story.state_apply_service import StoryStateApplyService  # noqa: F401

warnings.warn(
    "rp.services.story_state_apply_service is deprecated and will be removed next release; "
    "use rp.services.story.state_apply_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
