"""DEPRECATED: moved to rp.models.memory.contract_registry."""
from __future__ import annotations

import warnings

from rp.models.memory.contract_registry import *  # noqa: F401, F403

warnings.warn(
    "rp.models.memory_contract_registry is deprecated and will be removed next release; "
    "use rp.models.memory.contract_registry instead.",
    DeprecationWarning,
    stacklevel=2,
)
