"""DEPRECATED: moved to rp.models.setup_agent.stage."""
from __future__ import annotations

import warnings

from rp.models.setup_agent.stage import *  # noqa: F401, F403

warnings.warn(
    "rp.models.setup_stage is deprecated and will be removed next release; "
    "use rp.models.setup_agent.stage instead.",
    DeprecationWarning,
    stacklevel=2,
)
