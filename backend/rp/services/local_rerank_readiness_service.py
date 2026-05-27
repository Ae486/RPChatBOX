"""DEPRECATED: moved to rp.services.retrieval.local_rerank_readiness_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.local_rerank_readiness_service import *  # noqa: F401, F403
from rp.services.retrieval.local_rerank_readiness_service import (  # noqa: F401
    LocalRerankReadinessService,
)

warnings.warn(
    "rp.services.local_rerank_readiness_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.local_rerank_readiness_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
