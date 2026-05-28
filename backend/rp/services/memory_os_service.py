"""DEPRECATED: moved to rp.services.memory.os_service."""
from __future__ import annotations

import warnings

from rp.services.memory.os_service import *  # noqa: F401, F403
from rp.services.memory.os_service import MemoryOsService  # noqa: F401

warnings.warn(
    "rp.services.memory_os_service is deprecated and will be removed next release; "
    "use rp.services.memory.os_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
