"""DEPRECATED: moved to rp.services.retrieval.runtime_search_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.runtime_search_service import *  # noqa: F401, F403
from rp.services.retrieval.runtime_search_service import RuntimeRetrievalSearchService  # noqa: F401

warnings.warn(
    "rp.services.runtime_retrieval_search_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.runtime_search_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
