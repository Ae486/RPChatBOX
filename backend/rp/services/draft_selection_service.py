"""DEPRECATED: moved to rp.services.setup_agent.draft_selection_service."""
from __future__ import annotations

import warnings

from rp.services.setup_agent.draft_selection_service import *  # noqa: F401, F403
from rp.services.setup_agent.draft_selection_service import (  # noqa: F401
    DRAFT_ADOPTION_PAYLOAD_VERSION,
    DRAFT_SELECTION_PAYLOAD_VERSION,
    DraftSelectionService,
    DraftSelectionServiceError,
)

warnings.warn(
    "rp.services.draft_selection_service is deprecated and will be removed next release; "
    "use rp.services.setup_agent.draft_selection_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
