"""DEPRECATED: moved to rp.models.setup_agent.truth_index."""
from __future__ import annotations

import warnings

from rp.models.setup_agent.truth_index import *  # noqa: F401, F403

warnings.warn(
    "rp.models.setup_truth_index is deprecated and will be removed next release; "
    "use rp.models.setup_agent.truth_index instead.",
    DeprecationWarning,
    stacklevel=2,
)
