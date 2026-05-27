"""DEPRECATED: moved to rp.services.retrieval.block_adapter_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.block_adapter_service import *  # noqa: F401, F403
from rp.services.retrieval.block_adapter_service import RetrievalBlockAdapterService  # noqa: F401

warnings.warn(
    "rp.services.retrieval_block_adapter_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.block_adapter_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
