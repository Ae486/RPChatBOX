"""DEPRECATED: moved to rp.services.projection.compatibility_mirror_service."""
from __future__ import annotations

import warnings

from rp.services.projection.compatibility_mirror_service import *  # noqa: F401, F403
from rp.services.projection.compatibility_mirror_service import (  # noqa: F401
    ProjectionCompatibilityMirrorService,
)

warnings.warn(
    "rp.services.projection_compatibility_mirror_service is deprecated and will be "
    "removed next release; use rp.services.projection.compatibility_mirror_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
