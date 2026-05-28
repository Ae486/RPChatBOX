"""DEPRECATED: moved to rp.services.memory.provenance_read_service."""
from __future__ import annotations

import warnings

from rp.services.memory.provenance_read_service import *  # noqa: F401, F403
from rp.services.memory.provenance_read_service import ProvenanceReadService  # noqa: F401

warnings.warn(
    "rp.services.provenance_read_service is deprecated and will be removed next release; "
    "use rp.services.memory.provenance_read_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
