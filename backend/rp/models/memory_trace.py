"""DEPRECATED: moved to rp.models.memory.trace."""
from __future__ import annotations

import warnings

from rp.models.memory.trace import *  # noqa: F401, F403

warnings.warn(
    "rp.models.memory_trace is deprecated and will be removed next release; "
    "use rp.models.memory.trace instead.",
    DeprecationWarning,
    stacklevel=2,
)
