"""DEPRECATED: moved to rp.services.retrieval.service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.service import *  # noqa: F401, F403
from rp.services.retrieval.service import RetrievalService  # noqa: F401

warnings.warn(
    "rp.services.retrieval_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.service instead.",
    DeprecationWarning,
    stacklevel=2,
)
