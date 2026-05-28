"""DEPRECATED: moved to rp.services.proposal.service."""
from __future__ import annotations

import warnings

from rp.services.proposal.service import *  # noqa: F401, F403
from rp.services.proposal.service import ProposalService  # noqa: F401

warnings.warn(
    "rp.services.proposal_service is deprecated and will be removed next release; "
    "use rp.services.proposal.service instead.",
    DeprecationWarning,
    stacklevel=2,
)
