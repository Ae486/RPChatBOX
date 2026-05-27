"""DEPRECATED: moved to rp.services.retrieval.writer_usage_guard_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.writer_usage_guard_service import *  # noqa: F401, F403
from rp.services.retrieval.writer_usage_guard_service import (  # noqa: F401
    WriterRetrievalUsageGuardService,
    WriterRetrievalUsageGuardServiceError,
)

warnings.warn(
    "rp.services.writer_retrieval_usage_guard_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.writer_usage_guard_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
