"""DEPRECATED: moved to rp.models.runtime.workspace_material."""
from __future__ import annotations

import warnings

from rp.models.runtime.workspace_material import *  # noqa: F401, F403

warnings.warn(
    "rp.models.runtime_workspace_material is deprecated and will be removed next release; "
    "use rp.models.runtime.workspace_material instead.",
    DeprecationWarning,
    stacklevel=2,
)
