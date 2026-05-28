"""DEPRECATED: moved to rp.services.story.llm_gateway."""
from __future__ import annotations

import warnings

from rp.services.story.llm_gateway import *  # noqa: F401, F403
from rp.services.story.llm_gateway import StoryLlmGateway  # noqa: F401

warnings.warn(
    "rp.services.story_llm_gateway is deprecated and will be removed next release; "
    "use rp.services.story.llm_gateway instead.",
    DeprecationWarning,
    stacklevel=2,
)
