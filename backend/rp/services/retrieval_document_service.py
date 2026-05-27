"""DEPRECATED: moved to rp.services.retrieval.document_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.document_service import *  # noqa: F401, F403
from rp.services.retrieval.document_service import RetrievalDocumentService  # noqa: F401

warnings.warn(
    "rp.services.retrieval_document_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.document_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
