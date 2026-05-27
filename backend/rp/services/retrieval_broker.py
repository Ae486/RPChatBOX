"""DEPRECATED: moved to rp.services.retrieval.broker."""
from __future__ import annotations

import warnings

from rp.services.retrieval.broker import *  # noqa: F401, F403
from rp.services.retrieval.broker import RetrievalBroker  # noqa: F401

warnings.warn(
    "rp.services.retrieval_broker is deprecated and will be removed next release; "
    "use rp.services.retrieval.broker instead.",
    DeprecationWarning,
    stacklevel=2,
)
