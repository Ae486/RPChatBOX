"""DEPRECATED: moved to rp.services.proposal.post_write_scheduler_service."""
from __future__ import annotations

import warnings

from rp.services.proposal.post_write_scheduler_service import *  # noqa: F401, F403
from rp.services.proposal.post_write_scheduler_service import (  # noqa: F401
    POST_WRITE_MAINTENANCE_PHASE,
    PostWriteSchedulerService,
)

warnings.warn(
    "rp.services.post_write_scheduler_service is deprecated and will be removed next release; "
    "use rp.services.proposal.post_write_scheduler_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
