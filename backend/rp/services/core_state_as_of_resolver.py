"""DEPRECATED: moved to rp.services.core_state.as_of_resolver."""
from __future__ import annotations

import warnings

from rp.services.core_state.as_of_resolver import *  # noqa: F401, F403
from rp.services.core_state.as_of_resolver import CoreStateAsOfResolver  # noqa: F401

warnings.warn(
    "rp.services.core_state_as_of_resolver is deprecated and will be removed next release; "
    "use rp.services.core_state.as_of_resolver instead.",
    DeprecationWarning,
    stacklevel=2,
)
