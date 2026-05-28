"""DEPRECATED: moved to rp.services.runtime.profile_snapshot_service."""
from __future__ import annotations

import warnings

from rp.services.runtime.profile_snapshot_service import *  # noqa: F401, F403
from rp.services.runtime.profile_snapshot_service import (  # noqa: F401
    RuntimeProfileSnapshotService,
    RuntimeProfileSnapshotServiceError,
)

warnings.warn(
    "rp.services.runtime_profile_snapshot_service is deprecated and will be removed next release; "
    "use rp.services.runtime.profile_snapshot_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
