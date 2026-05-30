"""DEPRECATED: moved to rp.models.retrieval.runtime_contracts."""
from __future__ import annotations

import warnings

from rp.models.retrieval.runtime_contracts import *  # noqa: F401, F403

warnings.warn(
    "rp.models.retrieval_runtime_contracts is deprecated and will be removed next release; "
    "use rp.models.retrieval.runtime_contracts instead.",
    DeprecationWarning,
    stacklevel=2,
)
