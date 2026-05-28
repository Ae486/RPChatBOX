"""DEPRECATED: moved to rp.services.runtime.read_manifest_service."""
from __future__ import annotations

import warnings

from rp.services.runtime.read_manifest_service import *  # noqa: F401, F403
from rp.services.runtime.read_manifest_service import (  # noqa: F401
    BranchVisibilityResolver,
    RuntimeReadManifestService,
    RuntimeReadManifestServiceError,
    filter_hits_by_branch_visibility,
)

warnings.warn(
    "rp.services.runtime_read_manifest_service is deprecated and will be removed next release; "
    "use rp.services.runtime.read_manifest_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
