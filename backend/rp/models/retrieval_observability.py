"""DEPRECATED: moved to rp.models.retrieval.observability."""
from __future__ import annotations

import warnings

from rp.models.retrieval.observability import *  # noqa: F401, F403

warnings.warn(
    "rp.models.retrieval_observability is deprecated and will be removed next release; "
    "use rp.models.retrieval.observability instead.",
    DeprecationWarning,
    stacklevel=2,
)
