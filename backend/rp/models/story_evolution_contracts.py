"""DEPRECATED: moved to rp.models.story.evolution_contracts."""
from __future__ import annotations

import warnings

from rp.models.story.evolution_contracts import *  # noqa: F401, F403

warnings.warn(
    "rp.models.story_evolution_contracts is deprecated and will be removed next release; "
    "use rp.models.story.evolution_contracts instead.",
    DeprecationWarning,
    stacklevel=2,
)
