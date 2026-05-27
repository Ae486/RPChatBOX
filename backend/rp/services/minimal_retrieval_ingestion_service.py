"""DEPRECATED: moved to rp.services.retrieval.minimal_ingestion_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.minimal_ingestion_service import *  # noqa: F401, F403
from rp.services.retrieval.minimal_ingestion_service import (  # noqa: F401
    MinimalRetrievalIngestionService,
)

warnings.warn(
    "rp.services.minimal_retrieval_ingestion_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.minimal_ingestion_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
