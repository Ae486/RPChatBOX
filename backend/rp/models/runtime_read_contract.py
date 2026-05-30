"""DEPRECATED: moved to rp.models.runtime.read_contract."""
from __future__ import annotations

import warnings

from rp.models.runtime.read_contract import *  # noqa: F401, F403

warnings.warn(
    "rp.models.runtime_read_contract is deprecated and will be removed next release; "
    "use rp.models.runtime.read_contract instead.",
    DeprecationWarning,
    stacklevel=2,
)
