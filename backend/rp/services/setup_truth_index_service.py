"""DEPRECATED: moved to rp.services.setup_agent.truth_index_service."""
from __future__ import annotations

import warnings

from rp.services.setup_agent.truth_index_service import *  # noqa: F401, F403
from rp.services.setup_agent.truth_index_service import (  # noqa: F401
    SetupTruthIndexService,
)

warnings.warn(
    "rp.services.setup_truth_index_service is deprecated and will be removed next release; "
    "use rp.services.setup_agent.truth_index_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
