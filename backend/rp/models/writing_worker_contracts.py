"""DEPRECATED: moved to rp.models.writer.writing_worker_contracts."""
from __future__ import annotations

import warnings

from rp.models.writer.writing_worker_contracts import *  # noqa: F401, F403

warnings.warn(
    "rp.models.writing_worker_contracts is deprecated and will be removed next release; "
    "use rp.models.writer.writing_worker_contracts instead.",
    DeprecationWarning,
    stacklevel=2,
)
