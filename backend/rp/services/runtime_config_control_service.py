"""DEPRECATED: moved to rp.services.runtime.config_control_service."""
from __future__ import annotations

import warnings

from rp.services.runtime.config_control_service import *  # noqa: F401, F403
from rp.services.runtime.config_control_service import (  # noqa: F401
    RuntimeConfigControlService,
    RuntimeConfigControlServiceError,
)

warnings.warn(
    "rp.services.runtime_config_control_service is deprecated and will be removed next release; "
    "use rp.services.runtime.config_control_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
