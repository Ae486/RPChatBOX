"""DEPRECATED: moved to rp.services.story.session_core_state_adapter."""
from __future__ import annotations

import warnings

from rp.services.story.session_core_state_adapter import *  # noqa: F401, F403
from rp.services.story.session_core_state_adapter import StorySessionCoreStateAdapter  # noqa: F401

warnings.warn(
    "rp.services.story_session_core_state_adapter is deprecated and will be removed next release; "
    "use rp.services.story.session_core_state_adapter instead.",
    DeprecationWarning,
    stacklevel=2,
)
