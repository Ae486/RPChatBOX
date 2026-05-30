"""DEPRECATED: moved to rp.models.setup_agent.handoff."""
from __future__ import annotations

import warnings

from rp.models.setup_agent.handoff import *  # noqa: F401, F403

warnings.warn(
    "rp.models.setup_handoff is deprecated and will be removed next release; "
    "use rp.models.setup_agent.handoff instead.",
    DeprecationWarning,
    stacklevel=2,
)
