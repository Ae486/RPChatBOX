"""DEPRECATED: moved to rp.models.retrieval.records."""
from __future__ import annotations

import warnings

from rp.models.retrieval.records import *  # noqa: F401, F403

warnings.warn(
    "rp.models.retrieval_records is deprecated and will be removed next release; "
    "use rp.models.retrieval.records instead.",
    DeprecationWarning,
    stacklevel=2,
)
