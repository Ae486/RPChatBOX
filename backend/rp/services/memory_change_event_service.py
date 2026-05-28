"""DEPRECATED: moved to rp.services.memory.change_event_service."""
from __future__ import annotations

import warnings

from rp.services.memory.change_event_service import *  # noqa: F401, F403
from rp.services.memory.change_event_service import (  # noqa: F401
    MemoryChangeEventService,
    MemoryChangeEventServiceError,
    MemoryChangeEventStore,
)

warnings.warn(
    "rp.services.memory_change_event_service is deprecated and will be removed next release; "
    "use rp.services.memory.change_event_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
