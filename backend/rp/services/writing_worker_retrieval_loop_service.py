"""DEPRECATED: moved to rp.services.writer.writing_worker_retrieval_loop_service."""
from __future__ import annotations

import warnings

from rp.services.writer.writing_worker_retrieval_loop_service import *  # noqa: F401, F403
from rp.services.writer.writing_worker_retrieval_loop_service import (  # noqa: F401
    WRITER_RETRIEVAL_EXPAND_TOOL,
    WRITER_RETRIEVAL_SEARCH_TOOL,
    WRITER_RETRIEVAL_USAGE_TOOL,
    WriterRetrievalLoopResult,
    WritingWorkerRetrievalLoopService,
    WritingWorkerRetrievalLoopServiceError,
)

warnings.warn(
    "rp.services.writing_worker_retrieval_loop_service is deprecated and will be removed next release; "
    "use rp.services.writer.writing_worker_retrieval_loop_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
