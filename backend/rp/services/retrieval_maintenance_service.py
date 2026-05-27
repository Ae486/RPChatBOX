"""DEPRECATED: moved to rp.services.retrieval.maintenance_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.maintenance_service import *  # noqa: F401, F403
from rp.services.retrieval.maintenance_service import RetrievalMaintenanceService  # noqa: F401

warnings.warn(
    "rp.services.retrieval_maintenance_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.maintenance_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
