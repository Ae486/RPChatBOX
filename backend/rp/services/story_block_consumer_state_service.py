"""DEPRECATED: moved to rp.services.story.block_consumer_state_service."""
from __future__ import annotations

import warnings

from rp.services.story.block_consumer_state_service import *  # noqa: F401, F403
from rp.services.story.block_consumer_state_service import StoryBlockConsumerStateService  # noqa: F401

warnings.warn(
    "rp.services.story_block_consumer_state_service is deprecated and will be removed next release; "
    "use rp.services.story.block_consumer_state_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
