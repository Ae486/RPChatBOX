"""DEPRECATED: moved to rp.services.setup_agent.agent_prompt_service."""
from __future__ import annotations

import warnings

from rp.services.setup_agent.agent_prompt_service import *  # noqa: F401, F403
from rp.services.setup_agent.agent_prompt_service import (  # noqa: F401
    SetupAgentPromptService,
)

warnings.warn(
    "rp.services.setup_agent_prompt_service is deprecated and will be removed next release; "
    "use rp.services.setup_agent.agent_prompt_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
