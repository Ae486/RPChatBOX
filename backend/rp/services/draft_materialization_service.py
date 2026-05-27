"""DEPRECATED: moved to rp.services.setup_agent.draft_materialization_service."""
from __future__ import annotations

import warnings

from rp.services.setup_agent.draft_materialization_service import *  # noqa: F401, F403
from rp.services.setup_agent.draft_materialization_service import (  # noqa: F401
    DraftMaterializationService,
    MATERIALIZATION_VERSION,
)

warnings.warn(
    "rp.services.draft_materialization_service is deprecated and will be removed next release; "
    "use rp.services.setup_agent.draft_materialization_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
