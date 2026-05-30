"""DEPRECATED: moved to rp.models.writer.writing_runtime."""
from __future__ import annotations

import warnings

from rp.models.writer.writing_runtime import *  # noqa: F401, F403

warnings.warn(
    "rp.models.writing_runtime is deprecated and will be removed next release; "
    "use rp.models.writer.writing_runtime instead.",
    DeprecationWarning,
    stacklevel=2,
)
