"""DEPRECATED: moved to rp.services.core_state.read_service."""
from __future__ import annotations

import warnings

from rp.services.core_state.read_service import *  # noqa: F401, F403
from rp.services.core_state.read_service import CoreStateReadService  # noqa: F401

warnings.warn(
    "rp.services.core_state_read_service is deprecated and will be removed next release; "
    "use rp.services.core_state.read_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
