"""DEPRECATED: moved to rp.services.projection.settled_mapper."""
from __future__ import annotations

import warnings

from rp.services.projection.settled_mapper import *  # noqa: F401, F403
from rp.services.projection.settled_mapper import (  # noqa: F401
    SETTLED_PROJECTION_SLOT_ORDER,
    settled_projection_slots,
)

warnings.warn(
    "rp.services.settled_projection_mapper is deprecated and will be removed next "
    "release; use rp.services.projection.settled_mapper instead.",
    DeprecationWarning,
    stacklevel=2,
)
