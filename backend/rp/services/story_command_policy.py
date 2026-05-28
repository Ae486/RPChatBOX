"""DEPRECATED: moved to rp.services.story.command_policy."""
from __future__ import annotations

import warnings

from rp.services.story.command_policy import *  # noqa: F401, F403

warnings.warn(
    "rp.services.story_command_policy is deprecated and will be removed next release; "
    "use rp.services.story.command_policy instead.",
    DeprecationWarning,
    stacklevel=2,
)
