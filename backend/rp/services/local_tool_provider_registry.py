"""DEPRECATED: moved to rp.services.writer.local_tool_provider_registry."""
from __future__ import annotations

import warnings

from rp.services.writer.local_tool_provider_registry import *  # noqa: F401, F403
from rp.services.writer.local_tool_provider_registry import (  # noqa: F401
    LocalToolProviderRegistry,
)

warnings.warn(
    "rp.services.local_tool_provider_registry is deprecated and will be removed next release; "
    "use rp.services.writer.local_tool_provider_registry instead.",
    DeprecationWarning,
    stacklevel=2,
)
