"""DEPRECATED: moved to rp.services.writer.writing_worker_execution_service."""
from __future__ import annotations

import warnings

from rp.services.writer.writing_worker_execution_service import *  # noqa: F401, F403
from rp.services.writer.writing_worker_execution_service import (  # noqa: F401
    WritingWorkerExecutionService,
)

warnings.warn(
    "rp.services.writing_worker_execution_service is deprecated and will be removed next release; "
    "use rp.services.writer.writing_worker_execution_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
