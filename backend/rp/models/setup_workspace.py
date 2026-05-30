"""DEPRECATED: moved to rp.models.setup_agent.workspace."""
from __future__ import annotations

import warnings

from rp.models.setup_agent.workspace import *  # noqa: F401, F403

warnings.warn(
    "rp.models.setup_workspace is deprecated and will be removed next release; "
    "use rp.models.setup_agent.workspace instead.",
    DeprecationWarning,
    stacklevel=2,
)
