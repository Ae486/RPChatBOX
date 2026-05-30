"""DEPRECATED: moved to rp.models.memory.materialization."""
from __future__ import annotations

import warnings

from rp.models.memory.materialization import *  # noqa: F401, F403

warnings.warn(
    "rp.models.memory_materialization is deprecated and will be removed next release; "
    "use rp.models.memory.materialization instead.",
    DeprecationWarning,
    stacklevel=2,
)
