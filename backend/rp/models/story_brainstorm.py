"""DEPRECATED: moved to rp.models.story.brainstorm."""
from __future__ import annotations

import warnings

from rp.models.story.brainstorm import *  # noqa: F401, F403

warnings.warn(
    "rp.models.story_brainstorm is deprecated and will be removed next release; "
    "use rp.models.story.brainstorm instead.",
    DeprecationWarning,
    stacklevel=2,
)
