"""DEPRECATED: moved to rp.services.memory.crud_validation_service."""
from __future__ import annotations

import warnings

from rp.services.memory.crud_validation_service import *  # noqa: F401, F403
from rp.services.memory.crud_validation_service import MemoryCrudValidationService  # noqa: F401

warnings.warn(
    "rp.services.memory_crud_validation_service is deprecated and will be removed next release; "
    "use rp.services.memory.crud_validation_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
