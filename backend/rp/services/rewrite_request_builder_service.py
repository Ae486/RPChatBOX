"""DEPRECATED: moved to rp.services.writer.rewrite_request_builder_service."""
from __future__ import annotations

import warnings

from rp.services.writer.rewrite_request_builder_service import *  # noqa: F401, F403
from rp.services.writer.rewrite_request_builder_service import (  # noqa: F401
    RewriteRequestBuilderService,
    RewriteRequestBuilderServiceError,
    identity_created_at_placeholder,
)

warnings.warn(
    "rp.services.rewrite_request_builder_service is deprecated and will be removed next release; "
    "use rp.services.writer.rewrite_request_builder_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
