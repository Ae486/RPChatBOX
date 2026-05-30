"""DEPRECATED: moved to rp.models.runtime.config_contracts."""
from __future__ import annotations

import warnings

from rp.models.runtime.config_contracts import *  # noqa: F401, F403

warnings.warn(
    "rp.models.runtime_config_contracts is deprecated and will be removed next release; "
    "use rp.models.runtime.config_contracts instead.",
    DeprecationWarning,
    stacklevel=2,
)
