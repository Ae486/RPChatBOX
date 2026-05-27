"""DEPRECATED: moved to rp.services.retrieval.runtime_config_service."""
from __future__ import annotations

import warnings

from rp.services.retrieval.runtime_config_service import *  # noqa: F401, F403
from rp.services.retrieval.runtime_config_service import RetrievalRuntimeConfigService  # noqa: F401

warnings.warn(
    "rp.services.retrieval_runtime_config_service is deprecated and will be removed next release; "
    "use rp.services.retrieval.runtime_config_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
