"""DEPRECATED: moved to rp.models.writer.longform_chapter_contracts."""
from __future__ import annotations

import warnings

from rp.models.writer.longform_chapter_contracts import *  # noqa: F401, F403

warnings.warn(
    "rp.models.longform_chapter_contracts is deprecated and will be removed next release; "
    "use rp.models.writer.longform_chapter_contracts instead.",
    DeprecationWarning,
    stacklevel=2,
)
