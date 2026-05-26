"""DEPRECATED: moved to rp.services.recall.summary_ingestion_service."""
from __future__ import annotations

import warnings

from rp.services.recall.summary_ingestion_service import *  # noqa: F401, F403
from rp.services.recall.summary_ingestion_service import (  # noqa: F401
    RecallSummaryIngestionService,
)

warnings.warn(
    "rp.services.recall_summary_ingestion_service is deprecated and will be removed next "
    "release; use rp.services.recall.summary_ingestion_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
