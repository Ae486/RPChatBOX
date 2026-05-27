"""DEPRECATED: moved to rp.services.retrieval.collection_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.collection_service import *  # noqa: F401, F403
from rp.services.retrieval.collection_service import RetrievalCollectionService  # noqa: F401

warnings.warn(
    "rp.services.retrieval_collection_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.collection_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
