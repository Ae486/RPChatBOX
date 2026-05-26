"""DEPRECATED: moved to rp.services.projection.state_service."""
from __future__ import annotations

import warnings

from rp.services.projection.state_service import *  # noqa: F401, F403
from rp.services.projection.state_service import ProjectionStateService  # noqa: F401

warnings.warn(
    "rp.services.projection_state_service is deprecated and will be removed next release; "
    "use rp.services.projection.state_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
