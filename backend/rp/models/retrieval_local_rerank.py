"""DEPRECATED: moved to rp.models.retrieval.local_rerank."""
from __future__ import annotations

import warnings

from rp.models.retrieval.local_rerank import *  # noqa: F401, F403

warnings.warn(
    "rp.models.retrieval_local_rerank is deprecated and will be removed next release; "
    "use rp.models.retrieval.local_rerank instead.",
    DeprecationWarning,
    stacklevel=2,
)
