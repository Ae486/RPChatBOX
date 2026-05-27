"""DEPRECATED: moved to rp.services.setup_agent.commit_warning_service."""
from __future__ import annotations

import warnings

from rp.services.setup_agent.commit_warning_service import *  # noqa: F401, F403
from rp.services.setup_agent.commit_warning_service import (  # noqa: F401
    collect_setup_commit_warning_codes,
)

warnings.warn(
    "rp.services.setup_commit_warning_service is deprecated and will be removed next release; "
    "use rp.services.setup_agent.commit_warning_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
