"""DEPRECATED: moved to rp.services.story.activation_service."""
from __future__ import annotations

import warnings

from rp.services.story.activation_service import *  # noqa: F401, F403
from rp.services.story.activation_service import StoryActivationService  # noqa: F401

warnings.warn(
    "rp.services.story_activation_service is deprecated and will be removed next release; "
    "use rp.services.story.activation_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
