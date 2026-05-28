"""DEPRECATED: moved to rp.services.memory.graph_extraction_service."""
from __future__ import annotations

import warnings

from rp.services.memory.graph_extraction_service import *  # noqa: F401, F403
from rp.services.memory.graph_extraction_service import MemoryGraphExtractionService  # noqa: F401

warnings.warn(
    "rp.services.memory_graph_extraction_service is deprecated and will be removed next release; "
    "use rp.services.memory.graph_extraction_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
