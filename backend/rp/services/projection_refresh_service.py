"""DEPRECATED: moved to rp.services.projection.refresh_service."""
from __future__ import annotations

import warnings

from rp.services.projection.refresh_service import *  # noqa: F401, F403
from rp.services.projection.refresh_service import ProjectionRefreshService  # noqa: F401

warnings.warn(
    "rp.services.projection_refresh_service is deprecated and will be removed next release; "
    "use rp.services.projection.refresh_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
