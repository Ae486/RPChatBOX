"""DEPRECATED: moved to rp.models.shared.dsl."""
from __future__ import annotations

import warnings

from rp.models.shared.dsl import *  # noqa: F401, F403

warnings.warn(
    "rp.models.dsl is deprecated and will be removed next release; "
    "use rp.models.shared.dsl instead.",
    DeprecationWarning,
    stacklevel=2,
)
