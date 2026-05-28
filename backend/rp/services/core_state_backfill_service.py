"""DEPRECATED: moved to rp.services.core_state.backfill_service."""
from __future__ import annotations

import warnings

from rp.services.core_state.backfill_service import *  # noqa: F401, F403
from rp.services.core_state.backfill_service import CoreStateBackfillService  # noqa: F401

warnings.warn(
    "rp.services.core_state_backfill_service is deprecated and will be removed next release; "
    "use rp.services.core_state.backfill_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
