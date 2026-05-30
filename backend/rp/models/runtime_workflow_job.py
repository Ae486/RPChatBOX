"""DEPRECATED: moved to rp.models.runtime.workflow_job."""
from __future__ import annotations

import warnings

from rp.models.runtime.workflow_job import *  # noqa: F401, F403

warnings.warn(
    "rp.models.runtime_workflow_job is deprecated and will be removed next release; "
    "use rp.models.runtime.workflow_job instead.",
    DeprecationWarning,
    stacklevel=2,
)
