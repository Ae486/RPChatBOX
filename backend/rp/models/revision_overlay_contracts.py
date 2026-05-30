"""DEPRECATED: moved to rp.models.core_state.revision_overlay_contracts."""
from __future__ import annotations

import warnings

from rp.models.core_state.revision_overlay_contracts import *  # noqa: F401, F403

warnings.warn(
    "rp.models.revision_overlay_contracts is deprecated and will be removed next release; "
    "use rp.models.core_state.revision_overlay_contracts instead.",
    DeprecationWarning,
    stacklevel=2,
)
