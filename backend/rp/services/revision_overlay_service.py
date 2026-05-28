"""DEPRECATED: moved to rp.services.core_state.revision_overlay_service."""
from __future__ import annotations

import warnings

from rp.services.core_state.revision_overlay_service import *  # noqa: F401, F403
from rp.services.core_state.revision_overlay_service import RevisionOverlayService  # noqa: F401

warnings.warn(
    "rp.services.revision_overlay_service is deprecated and will be removed next release; "
    "use rp.services.core_state.revision_overlay_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
