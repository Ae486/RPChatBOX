"""DEPRECATED: moved to rp.services.writer.rewrite_candidate_service."""
from __future__ import annotations

import warnings

from rp.services.writer.rewrite_candidate_service import *  # noqa: F401, F403
from rp.services.writer.rewrite_candidate_service import (  # noqa: F401
    REWRITE_CANDIDATE_PAYLOAD_VERSION,
    RewriteCandidateService,
    RewriteCandidateServiceError,
)

warnings.warn(
    "rp.services.rewrite_candidate_service is deprecated and will be removed next release; "
    "use rp.services.writer.rewrite_candidate_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
