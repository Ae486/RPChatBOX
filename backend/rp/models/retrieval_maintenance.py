"""DEPRECATED: moved to rp.models.retrieval.maintenance."""
from __future__ import annotations

import warnings

from rp.models.retrieval.maintenance import *  # noqa: F401, F403

warnings.warn(
    "rp.models.retrieval_maintenance is deprecated and will be removed next release; "
    "use rp.models.retrieval.maintenance instead.",
    DeprecationWarning,
    stacklevel=2,
)
