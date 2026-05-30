"""DEPRECATED: moved to rp.models.block.prompt_context."""
from __future__ import annotations

import warnings

from rp.models.block.prompt_context import *  # noqa: F401, F403

warnings.warn(
    "rp.models.block_prompt_context is deprecated and will be removed next release; "
    "use rp.models.block.prompt_context instead.",
    DeprecationWarning,
    stacklevel=2,
)
