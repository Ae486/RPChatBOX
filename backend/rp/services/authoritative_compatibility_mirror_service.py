"""DEPRECATED: moved to rp.services.core_state.authoritative_compatibility_mirror_service."""
from __future__ import annotations

import warnings

from rp.services.core_state.authoritative_compatibility_mirror_service import *  # noqa: F401, F403
from rp.services.core_state.authoritative_compatibility_mirror_service import AuthoritativeCompatibilityMirrorService  # noqa: F401

warnings.warn(
    "rp.services.authoritative_compatibility_mirror_service is deprecated and will be removed next release; "
    "use rp.services.core_state.authoritative_compatibility_mirror_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
