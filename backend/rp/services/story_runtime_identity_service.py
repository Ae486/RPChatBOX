"""DEPRECATED: moved to rp.services.story.runtime_identity_service."""
from __future__ import annotations

import warnings

from rp.services.story.runtime_identity_service import *  # noqa: F401, F403
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityServiceError, StoryRuntimeIdentityService  # noqa: F401

warnings.warn(
    "rp.services.story_runtime_identity_service is deprecated and will be removed next release; "
    "use rp.services.story.runtime_identity_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
