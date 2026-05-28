"""DEPRECATED: moved to rp.services.core_state.authoritative_state_view_service."""
from __future__ import annotations

import warnings

from rp.services.core_state.authoritative_state_view_service import *  # noqa: F401, F403
from rp.services.core_state.authoritative_state_view_service import AuthoritativeStateViewService  # noqa: F401

warnings.warn(
    "rp.services.authoritative_state_view_service is deprecated and will be removed next release; "
    "use rp.services.core_state.authoritative_state_view_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
