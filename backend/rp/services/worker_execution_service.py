"""DEPRECATED: moved to rp.services.writer.worker_execution_service."""
from __future__ import annotations

import warnings

from rp.services.writer.worker_execution_service import *  # noqa: F401, F403
from rp.services.writer.worker_execution_service import (  # noqa: F401
    WorkerExecutionOutcome,
    WorkerExecutionService,
    WorkerExecutionServiceError,
)

warnings.warn(
    "rp.services.worker_execution_service is deprecated and will be removed next release; "
    "use rp.services.writer.worker_execution_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
