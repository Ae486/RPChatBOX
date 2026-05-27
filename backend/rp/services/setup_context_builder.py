"""DEPRECATED: moved to rp.services.setup_agent.context_builder."""
from __future__ import annotations

import warnings

from rp.services.setup_agent.context_builder import *  # noqa: F401, F403
from rp.services.setup_agent.context_builder import SetupContextBuilder  # noqa: F401

warnings.warn(
    "rp.services.setup_context_builder is deprecated and will be removed next release; "
    "use rp.services.setup_agent.context_builder instead.",
    DeprecationWarning,
    stacklevel=2,
)
