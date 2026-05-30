"""DEPRECATED: moved to rp.models.proposal.postwrite_runtime_contracts."""
from __future__ import annotations

import warnings

from rp.models.proposal.postwrite_runtime_contracts import *  # noqa: F401, F403

warnings.warn(
    "rp.models.postwrite_runtime_contracts is deprecated and will be removed next release; "
    "use rp.models.proposal.postwrite_runtime_contracts instead.",
    DeprecationWarning,
    stacklevel=2,
)
