"""DEPRECATED: moved to rp.services.proposal.repository."""
from __future__ import annotations

import warnings

from rp.services.proposal.repository import *  # noqa: F401, F403
from rp.services.proposal.repository import (  # noqa: F401
    ProposalRepository,
    extract_core_mutation_envelope,
    extract_worker_governance_metadata,
)

warnings.warn(
    "rp.services.proposal_repository is deprecated and will be removed next release; "
    "use rp.services.proposal.repository instead.",
    DeprecationWarning,
    stacklevel=2,
)
