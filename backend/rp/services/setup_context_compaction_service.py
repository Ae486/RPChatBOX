"""DEPRECATED: moved to rp.services.setup_agent.context_compaction_service."""
from __future__ import annotations

import warnings

from rp.services.setup_agent.context_compaction_service import *  # noqa: F401, F403
from rp.services.setup_agent.context_compaction_service import (  # noqa: F401
    SetupContextCompactionService,
)

warnings.warn(
    "rp.services.setup_context_compaction_service is deprecated and will be removed next release; "
    "use rp.services.setup_agent.context_compaction_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
