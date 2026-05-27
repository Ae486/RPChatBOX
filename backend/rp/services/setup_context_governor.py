"""DEPRECATED: moved to rp.services.setup_agent.context_governor."""
from __future__ import annotations

import warnings

from rp.services.setup_agent.context_governor import *  # noqa: F401, F403
from rp.services.setup_agent.context_governor import (  # noqa: F401
    SetupContextGovernorService,
)

warnings.warn(
    "rp.services.setup_context_governor is deprecated and will be removed next release; "
    "use rp.services.setup_agent.context_governor instead.",
    DeprecationWarning,
    stacklevel=2,
)
