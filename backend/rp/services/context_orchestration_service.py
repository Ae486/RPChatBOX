"""DEPRECATED: moved to rp.services.runtime.context_orchestration_service."""
from __future__ import annotations

import warnings

from rp.services.runtime.context_orchestration_service import *  # noqa: F401, F403
from rp.services.runtime.context_orchestration_service import (  # noqa: F401
    ContextOrchestrationService,
)

warnings.warn(
    "rp.services.context_orchestration_service is deprecated and will be removed next release; "
    "use rp.services.runtime.context_orchestration_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
