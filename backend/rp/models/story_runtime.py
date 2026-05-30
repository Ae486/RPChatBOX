"""DEPRECATED: moved to rp.models.story.runtime."""
from __future__ import annotations

import warnings

from rp.models.story.runtime import *  # noqa: F401, F403

warnings.warn(
    "rp.models.story_runtime is deprecated and will be removed next release; "
    "use rp.models.story.runtime instead.",
    DeprecationWarning,
    stacklevel=2,
)
