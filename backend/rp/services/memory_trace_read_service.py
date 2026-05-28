"""DEPRECATED: moved to rp.services.memory.trace_read_service."""
from __future__ import annotations

import warnings

from rp.services.memory.trace_read_service import *  # noqa: F401, F403
from rp.services.memory.trace_read_service import MemoryTraceReadService  # noqa: F401

warnings.warn(
    "rp.services.memory_trace_read_service is deprecated and will be removed next release; "
    "use rp.services.memory.trace_read_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
