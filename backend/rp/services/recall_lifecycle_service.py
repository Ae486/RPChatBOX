"""DEPRECATED: moved to rp.services.recall.lifecycle_service."""
from __future__ import annotations

import warnings

from rp.services.recall.lifecycle_service import *  # noqa: F401, F403
from rp.services.recall.lifecycle_service import RecallLifecycleService  # noqa: F401

warnings.warn(
    "rp.services.recall_lifecycle_service is deprecated and will be removed next release; "
    "use rp.services.recall.lifecycle_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
