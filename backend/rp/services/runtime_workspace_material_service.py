"""DEPRECATED: moved to rp.services.runtime.workspace_material_service."""
from __future__ import annotations

import warnings

from rp.services.runtime.workspace_material_service import *  # noqa: F401, F403
from rp.services.runtime.workspace_material_service import (  # noqa: F401
    RUNTIME_WORKSPACE_TRACE_ROLE,
    RuntimeWorkspaceMaterialService,
    RuntimeWorkspaceMaterialServiceError,
    RuntimeWorkspaceMaterialStore,
)

warnings.warn(
    "rp.services.runtime_workspace_material_service is deprecated and will be removed next release; "
    "use rp.services.runtime.workspace_material_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
