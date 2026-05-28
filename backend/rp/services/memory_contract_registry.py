"""DEPRECATED: moved to rp.services.memory.contract_registry."""
from __future__ import annotations

import warnings

from rp.services.memory.contract_registry import *  # noqa: F401, F403
from rp.services.memory.contract_registry import (  # noqa: F401
    ARCHIVAL_LAYER,
    BOOTSTRAP_MEMORY_CONTRACT_REGISTRY_VERSION,
    BOOTSTRAP_MEMORY_DOMAIN_IDS,
    BOOTSTRAP_MEMORY_WORKER_IDS,
    CORE_STATE_AUTHORITATIVE_LAYER,
    CORE_STATE_PROJECTION_LAYER,
    DEFAULT_ALLOWED_LAYERS,
    LONGFORM_ACTIVE_DOMAIN_IDS,
    MemoryContractRegistryError,
    MemoryContractRegistryService,
    RECALL_LAYER,
    ROLEPLAY_ACTIVE_DOMAIN_IDS,
    RUNTIME_WORKSPACE_LAYER,
    TRPG_ACTIVE_DOMAIN_IDS,
    build_bootstrap_memory_contract_registry,
)

warnings.warn(
    "rp.services.memory_contract_registry is deprecated and will be removed next release; "
    "use rp.services.memory.contract_registry instead.",
    DeprecationWarning,
    stacklevel=2,
)
