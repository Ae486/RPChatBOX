"""DEPRECATED: moved to rp.services.setup_agent.runtime_controller."""
from __future__ import annotations

import warnings

from rp.services.setup_agent.runtime_controller import *  # noqa: F401, F403
from rp.services.setup_agent.runtime_controller import (  # noqa: F401
    SetupRuntimeController,
)

warnings.warn(
    "rp.services.setup_runtime_controller is deprecated and will be removed next release; "
    "use rp.services.setup_agent.runtime_controller instead.",
    DeprecationWarning,
    stacklevel=2,
)
