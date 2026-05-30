"""DEPRECATED: moved to rp.models.memory.inspection."""
from __future__ import annotations

import warnings

from rp.models.memory.inspection import *  # noqa: F401, F403

warnings.warn(
    "rp.models.memory_inspection is deprecated and will be removed next release; "
    "use rp.models.memory.inspection instead.",
    DeprecationWarning,
    stacklevel=2,
)
