"""DEPRECATED: moved to rp.services.proposal.workflow_service."""
from __future__ import annotations

import warnings

from rp.services.proposal.workflow_service import *  # noqa: F401, F403
from rp.services.proposal.workflow_service import ProposalWorkflowService  # noqa: F401

warnings.warn(
    "rp.services.proposal_workflow_service is deprecated and will be removed next release; "
    "use rp.services.proposal.workflow_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
