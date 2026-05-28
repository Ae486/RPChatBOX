"""DEPRECATED: moved to rp.services.story.block_mutation_service."""
from __future__ import annotations

import warnings

from rp.services.story.block_mutation_service import *  # noqa: F401, F403
from rp.services.story.block_mutation_service import MemoryBlockMutationUnsupportedError, MemoryBlockTargetMismatchError, MemoryBlockProposalNotFoundError, StoryBlockMutationService  # noqa: F401

warnings.warn(
    "rp.services.story_block_mutation_service is deprecated and will be removed next release; "
    "use rp.services.story.block_mutation_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
