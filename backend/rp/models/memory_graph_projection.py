"""DEPRECATED: moved to rp.models.memory.graph_projection."""
from __future__ import annotations

import warnings

from rp.models.memory.graph_projection import *  # noqa: F401, F403

warnings.warn(
    "rp.models.memory_graph_projection is deprecated and will be removed next release; "
    "use rp.models.memory.graph_projection instead.",
    DeprecationWarning,
    stacklevel=2,
)
