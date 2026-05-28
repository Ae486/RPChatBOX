"""DEPRECATED: moved to rp.services.runtime.workflow_job_service."""
from __future__ import annotations

import warnings

from rp.services.runtime.workflow_job_service import *  # noqa: F401, F403
from rp.services.runtime.workflow_job_service import (  # noqa: F401
    RuntimeWorkflowJobService,
    RuntimeWorkflowJobServiceError,
    TurnSettlementEvaluation,
)

warnings.warn(
    "rp.services.runtime_workflow_job_service is deprecated and will be removed next release; "
    "use rp.services.runtime.workflow_job_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
