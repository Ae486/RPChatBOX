"""DEPRECATED: moved to rp.models.memory.crud."""
from __future__ import annotations

import warnings

from rp.models.memory.crud import *  # noqa: F401, F403

warnings.warn(
    "rp.models.memory_crud is deprecated and will be removed next release; "
    "use rp.models.memory.crud instead.",
    DeprecationWarning,
    stacklevel=2,
)
