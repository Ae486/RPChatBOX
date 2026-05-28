"""DEPRECATED: moved to rp.services.memory.graph_projection_repository."""
from __future__ import annotations

import warnings

from rp.services.memory.graph_projection_repository import *  # noqa: F401, F403
from rp.services.memory.graph_projection_repository import MemoryGraphProjectionRepository  # noqa: F401

warnings.warn(
    "rp.services.memory_graph_projection_repository is deprecated and will be removed next release; "
    "use rp.services.memory.graph_projection_repository instead.",
    DeprecationWarning,
    stacklevel=2,
)
