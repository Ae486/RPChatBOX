"""DEPRECATED: moved to rp.models.proposal.core_mutation."""
from __future__ import annotations

import warnings

from rp.models.proposal.core_mutation import *  # noqa: F401, F403

warnings.warn(
    "rp.models.core_mutation is deprecated and will be removed next release; "
    "use rp.models.proposal.core_mutation instead.",
    DeprecationWarning,
    stacklevel=2,
)
