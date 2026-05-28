"""DEPRECATED: moved to rp.services.writer.longform_specialist_service."""
from __future__ import annotations

import warnings

from rp.services.writer.longform_specialist_service import *  # noqa: F401, F403
from rp.services.writer.longform_specialist_service import (  # noqa: F401
    LongformSpecialistService,
)

warnings.warn(
    "rp.services.longform_specialist_service is deprecated and will be removed next release; "
    "use rp.services.writer.longform_specialist_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
