"""DEPRECATED: moved to rp.services.writer.worker_memory_service."""
from __future__ import annotations

import warnings

from rp.services.writer.worker_memory_service import *  # noqa: F401, F403
from rp.services.writer.worker_memory_service import (  # noqa: F401
    WorkerMemoryPermissionError,
    WorkerMemoryService,
)

warnings.warn(
    "rp.services.worker_memory_service is deprecated and will be removed next release; "
    "use rp.services.writer.worker_memory_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
