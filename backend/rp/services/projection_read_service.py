"""DEPRECATED: moved to rp.services.projection.read_service."""
from __future__ import annotations

import warnings

from rp.services.projection.read_service import *  # noqa: F401, F403
from rp.services.projection.read_service import ProjectionReadService  # noqa: F401

warnings.warn(
    "rp.services.projection_read_service is deprecated and will be removed next release; "
    "use rp.services.projection.read_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
