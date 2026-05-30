"""DEPRECATED: moved to rp.models.block.prompt_compile."""
from __future__ import annotations

import warnings

from rp.models.block.prompt_compile import *  # noqa: F401, F403

warnings.warn(
    "rp.models.block_prompt_compile is deprecated and will be removed next release; "
    "use rp.models.block.prompt_compile instead.",
    DeprecationWarning,
    stacklevel=2,
)
