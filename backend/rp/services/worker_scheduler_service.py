"""DEPRECATED: moved to rp.services.writer.worker_scheduler_service."""
from __future__ import annotations

import warnings

from rp.services.writer.worker_scheduler_service import *  # noqa: F401, F403
from rp.services.writer.worker_scheduler_service import (  # noqa: F401
    PRE_WRITE_CONTEXT_PHASE,
    WorkerSchedulerService,
)

warnings.warn(
    "rp.services.worker_scheduler_service is deprecated and will be removed next release; "
    "use rp.services.writer.worker_scheduler_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
