"""DEPRECATED: moved to rp.models.story.archival_evolution."""
from __future__ import annotations

import warnings

from rp.models.story.archival_evolution import *  # noqa: F401, F403

warnings.warn(
    "rp.models.archival_evolution is deprecated and will be removed next release; "
    "use rp.models.story.archival_evolution instead.",
    DeprecationWarning,
    stacklevel=2,
)
