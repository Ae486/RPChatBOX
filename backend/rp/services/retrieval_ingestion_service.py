"""DEPRECATED: moved to rp.services.retrieval.ingestion_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.ingestion_service import *  # noqa: F401, F403
from rp.services.retrieval.ingestion_service import RetrievalIngestionService  # noqa: F401

warnings.warn(
    "rp.services.retrieval_ingestion_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.ingestion_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
