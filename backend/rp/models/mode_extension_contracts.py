"""DEPRECATED: moved to rp.models.runtime.mode_extension_contracts."""
from __future__ import annotations

import warnings

from rp.models.runtime.mode_extension_contracts import *  # noqa: F401, F403

warnings.warn(
    "rp.models.mode_extension_contracts is deprecated and will be removed next release; "
    "use rp.models.runtime.mode_extension_contracts instead.",
    DeprecationWarning,
    stacklevel=2,
)
