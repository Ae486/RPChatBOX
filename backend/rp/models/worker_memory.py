"""DEPRECATED: moved to rp.models.writer.worker_memory."""
from __future__ import annotations

import warnings

from rp.models.writer.worker_memory import *  # noqa: F401, F403

warnings.warn(
    "rp.models.worker_memory is deprecated and will be removed next release; "
    "use rp.models.writer.worker_memory instead.",
    DeprecationWarning,
    stacklevel=2,
)
