"""DEPRECATED: moved to rp.services.writer.worker_registry_service."""
from __future__ import annotations

import warnings

from rp.services.writer.worker_registry_service import *  # noqa: F401, F403
from rp.services.writer.worker_registry_service import (  # noqa: F401
    LONGFORM_MEMORY_WORKER_ID,
    ROLEPLAY_EXTENSION_SOURCE_WORKER_ID,
    TRPG_EXTENSION_SOURCE_WORKER_ID,
    WRITING_WORKER_ID,
    WorkerRegistryService,
    WorkerRegistryServiceError,
)

warnings.warn(
    "rp.services.worker_registry_service is deprecated and will be removed next release; "
    "use rp.services.writer.worker_registry_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
