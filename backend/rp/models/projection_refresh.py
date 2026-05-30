"""DEPRECATED: moved to rp.models.projection.refresh."""
from __future__ import annotations

import warnings

from rp.models.projection.refresh import *  # noqa: F401, F403

warnings.warn(
    "rp.models.projection_refresh is deprecated and will be removed next release; "
    "use rp.models.projection.refresh instead.",
    DeprecationWarning,
    stacklevel=2,
)
