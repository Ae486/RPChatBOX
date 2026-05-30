"""DEPRECATED: moved to rp.models.block.view."""
from __future__ import annotations

import warnings

from rp.models.block.view import *  # noqa: F401, F403

warnings.warn(
    "rp.models.block_view is deprecated and will be removed next release; "
    "use rp.models.block.view instead.",
    DeprecationWarning,
    stacklevel=2,
)
