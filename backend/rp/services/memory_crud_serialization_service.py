"""DEPRECATED: moved to rp.services.memory.crud_serialization_service."""
from __future__ import annotations

import warnings

from rp.services.memory.crud_serialization_service import *  # noqa: F401, F403
from rp.services.memory.crud_serialization_service import MemoryCrudSerializationService  # noqa: F401

warnings.warn(
    "rp.services.memory_crud_serialization_service is deprecated and will be removed next release; "
    "use rp.services.memory.crud_serialization_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
