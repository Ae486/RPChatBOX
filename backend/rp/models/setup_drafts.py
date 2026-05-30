"""DEPRECATED: moved to rp.models.setup_agent.drafts."""
from __future__ import annotations

import warnings

from rp.models.setup_agent.drafts import *  # noqa: F401, F403

warnings.warn(
    "rp.models.setup_drafts is deprecated and will be removed next release; "
    "use rp.models.setup_agent.drafts instead.",
    DeprecationWarning,
    stacklevel=2,
)
