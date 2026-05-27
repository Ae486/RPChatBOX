"""DEPRECATED: moved to rp.services.retrieval.observability_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.observability_service import *  # noqa: F401, F403
from rp.services.retrieval.observability_service import RetrievalObservabilityService  # noqa: F401

warnings.warn(
    "rp.services.retrieval_observability_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.observability_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
