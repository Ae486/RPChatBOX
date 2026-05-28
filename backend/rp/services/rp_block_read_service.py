"""DEPRECATED: moved to rp.services.memory.rp_block_read_service."""
from __future__ import annotations

import warnings

from rp.services.memory.rp_block_read_service import *  # noqa: F401, F403
from rp.services.memory.rp_block_read_service import RpBlockReadService  # noqa: F401

warnings.warn(
    "rp.services.rp_block_read_service is deprecated and will be removed next release; "
    "use rp.services.memory.rp_block_read_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
