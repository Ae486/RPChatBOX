"""DEPRECATED: moved to rp.services.runtime.memory_persistence_repository."""
from __future__ import annotations

import warnings

from rp.services.runtime.memory_persistence_repository import *  # noqa: F401, F403
from rp.services.runtime.memory_persistence_repository import (  # noqa: F401
    MemoryChangeEventRepository,
    RuntimeWorkspaceMaterialRepository,
    clone_json_value,
    identity_filters,
    normalize_optional_key,
    utcnow,
)

warnings.warn(
    "rp.services.runtime_memory_persistence_repository is deprecated and will be removed next release; "
    "use rp.services.runtime.memory_persistence_repository instead.",
    DeprecationWarning,
    stacklevel=2,
)
