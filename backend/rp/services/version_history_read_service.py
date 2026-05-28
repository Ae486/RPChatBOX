"""DEPRECATED: moved to rp.services.memory.version_history_read_service."""
from __future__ import annotations

import warnings

from rp.services.memory.version_history_read_service import *  # noqa: F401, F403
from rp.services.memory.version_history_read_service import VersionHistoryReadService  # noqa: F401

warnings.warn(
    "rp.services.version_history_read_service is deprecated and will be removed next release; "
    "use rp.services.memory.version_history_read_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
