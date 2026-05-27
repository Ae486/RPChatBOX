"""DEPRECATED: moved to rp.services.retrieval.runtime_card_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.runtime_card_service import *  # noqa: F401, F403
from rp.services.retrieval.runtime_card_service import (  # noqa: F401
    RuntimeRetrievalCardService,
    RuntimeRetrievalCardServiceError,
)

warnings.warn(
    "rp.services.runtime_retrieval_card_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.runtime_card_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
