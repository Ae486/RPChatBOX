"""DEPRECATED: moved to rp.models.retrieval.runtime_config."""
from __future__ import annotations

import warnings

from rp.models.retrieval.runtime_config import *  # noqa: F401, F403

warnings.warn(
    "rp.models.retrieval_runtime_config is deprecated and will be removed next release; "
    "use rp.models.retrieval.runtime_config instead.",
    DeprecationWarning,
    stacklevel=2,
)
