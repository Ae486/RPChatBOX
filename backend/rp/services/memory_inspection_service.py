"""DEPRECATED: moved to rp.services.memory.inspection_service."""
from __future__ import annotations

import warnings

from rp.services.memory.inspection_service import *  # noqa: F401, F403
from rp.services.memory.inspection_service import MemoryInspectionError, MemoryInspectionService  # noqa: F401

warnings.warn(
    "rp.services.memory_inspection_service is deprecated and will be removed next release; "
    "use rp.services.memory.inspection_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
