"""DEPRECATED: moved to rp.services.retrieval.index_job_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.index_job_service import *  # noqa: F401, F403
from rp.services.retrieval.index_job_service import RetrievalIndexJobService  # noqa: F401

warnings.warn(
    "rp.services.retrieval_index_job_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.index_job_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
