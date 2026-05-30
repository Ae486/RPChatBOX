"""DEPRECATED: moved to rp.models.runtime.identity."""
from __future__ import annotations

import warnings

from rp.models.runtime.identity import *  # noqa: F401, F403

warnings.warn(
    "rp.models.runtime_identity is deprecated and will be removed next release; "
    "use rp.models.runtime.identity instead.",
    DeprecationWarning,
    stacklevel=2,
)
