"""DEPRECATED: moved to rp.services.memory.registry_management_service."""
from __future__ import annotations

import warnings

from rp.services.memory.registry_management_service import *  # noqa: F401, F403
from rp.services.memory.registry_management_service import (  # noqa: F401
    MemoryRegistryManagementService,
    MemoryRegistryManagementServiceError,
)

warnings.warn(
    "rp.services.memory_registry_management_service is deprecated and will be removed next release; "
    "use rp.services.memory.registry_management_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
