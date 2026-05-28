"""DEPRECATED: moved to rp.services.proposal.apply_service."""
from __future__ import annotations

import warnings

from rp.services.proposal.apply_service import *  # noqa: F401, F403
from rp.services.proposal.apply_service import ProposalApplyService  # noqa: F401

warnings.warn(
    "rp.services.proposal_apply_service is deprecated and will be removed next release; "
    "use rp.services.proposal.apply_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
