"""DEPRECATED: moved to rp.services.story.evolution_service."""
from __future__ import annotations

import warnings

from rp.services.story.evolution_service import *  # noqa: F401, F403
from rp.services.story.evolution_service import StoryEvolutionServiceError, StoryEvolutionService  # noqa: F401

warnings.warn(
    "rp.services.story_evolution_service is deprecated and will be removed next release; "
    "use rp.services.story.evolution_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
