"""DEPRECATED: moved to rp.services.story.runtime_migration_service."""
from __future__ import annotations

import warnings

from rp.services.story.runtime_migration_service import *  # noqa: F401, F403
from rp.services.story.runtime_migration_service import StoryRuntimeMigrationService  # noqa: F401

warnings.warn(
    "rp.services.story_runtime_migration_service is deprecated and will be removed next release; "
    "use rp.services.story.runtime_migration_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
