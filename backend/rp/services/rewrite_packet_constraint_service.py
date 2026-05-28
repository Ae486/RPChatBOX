"""DEPRECATED: moved to rp.services.writer.rewrite_packet_constraint_service."""
from __future__ import annotations

import warnings

from rp.services.writer.rewrite_packet_constraint_service import *  # noqa: F401, F403
from rp.services.writer.rewrite_packet_constraint_service import (  # noqa: F401
    RewritePacketConstraintResult,
    RewritePacketConstraintService,
    RewritePacketConstraintServiceError,
)

warnings.warn(
    "rp.services.rewrite_packet_constraint_service is deprecated and will be removed next release; "
    "use rp.services.writer.rewrite_packet_constraint_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
