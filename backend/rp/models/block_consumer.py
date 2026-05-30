"""DEPRECATED: moved to rp.models.block.consumer."""
from __future__ import annotations

import warnings

from rp.models.block.consumer import *  # noqa: F401, F403

warnings.warn(
    "rp.models.block_consumer is deprecated and will be removed next release; "
    "use rp.models.block.consumer instead.",
    DeprecationWarning,
    stacklevel=2,
)
