"""DEPRECATED: moved to rp.services.core_state.store_repository."""
from __future__ import annotations

import warnings

from rp.services.core_state.store_repository import *  # noqa: F401, F403
from rp.services.core_state.store_repository import CoreStateStoreRepository  # noqa: F401

warnings.warn(
    "rp.services.core_state_store_repository is deprecated and will be removed next release; "
    "use rp.services.core_state.store_repository instead.",
    DeprecationWarning,
    stacklevel=2,
)
