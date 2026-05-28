"""DEPRECATED: moved to rp.services.story.block_prompt_render_service."""
from __future__ import annotations

import warnings

from rp.services.story.block_prompt_render_service import *  # noqa: F401, F403
from rp.services.story.block_prompt_render_service import StoryBlockPromptRenderService  # noqa: F401

warnings.warn(
    "rp.services.story_block_prompt_render_service is deprecated and will be removed next release; "
    "use rp.services.story.block_prompt_render_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
