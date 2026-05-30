"""DEPRECATED: moved to rp.models.proposal.post_write_policy."""
from __future__ import annotations

import warnings

from rp.models.proposal.post_write_policy import *  # noqa: F401, F403

warnings.warn(
    "rp.models.post_write_policy is deprecated and will be removed next release; "
    "use rp.models.proposal.post_write_policy instead.",
    DeprecationWarning,
    stacklevel=2,
)
