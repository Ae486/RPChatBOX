"""DEPRECATED: moved to rp.services.story.turn_domain_service."""
from __future__ import annotations

import warnings

from rp.services.story.turn_domain_service import *  # noqa: F401, F403
from rp.services.story.turn_domain_service import StoryTurnDomainService  # noqa: F401

warnings.warn(
    "rp.services.story_turn_domain_service is deprecated and will be removed next release; "
    "use rp.services.story.turn_domain_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
