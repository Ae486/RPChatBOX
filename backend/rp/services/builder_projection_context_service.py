"""DEPRECATED: moved to rp.services.projection.builder_context_service."""
from __future__ import annotations

import warnings

from rp.services.projection.builder_context_service import *  # noqa: F401, F403
from rp.services.projection.builder_context_service import (  # noqa: F401
    BuilderProjectionContextService,
)

warnings.warn(
    "rp.services.builder_projection_context_service is deprecated and will be "
    "removed next release; use rp.services.projection.builder_context_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
