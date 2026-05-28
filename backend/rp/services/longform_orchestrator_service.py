"""DEPRECATED: moved to rp.services.writer.longform_orchestrator_service."""
from __future__ import annotations

import warnings

from rp.services.writer.longform_orchestrator_service import *  # noqa: F401, F403
from rp.services.writer.longform_orchestrator_service import (  # noqa: F401
    LongformOrchestratorService,
)

warnings.warn(
    "rp.services.longform_orchestrator_service is deprecated and will be removed next release; "
    "use rp.services.writer.longform_orchestrator_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
