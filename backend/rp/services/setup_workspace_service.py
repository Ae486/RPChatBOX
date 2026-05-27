"""DEPRECATED: moved to rp.services.setup_agent.workspace_service."""
from __future__ import annotations

import warnings

from rp.services.setup_agent.workspace_service import *  # noqa: F401, F403
from rp.services.setup_agent.workspace_service import (  # noqa: F401
    SetupWorkspaceService,
)

warnings.warn(
    "rp.services.setup_workspace_service is deprecated and will be removed next release; "
    "use rp.services.setup_agent.workspace_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
