"""DEPRECATED: moved to rp.services.writer.longform_chapter_runtime_service."""
from __future__ import annotations

import warnings

from rp.services.writer.longform_chapter_runtime_service import *  # noqa: F401, F403
from rp.services.writer.longform_chapter_runtime_service import (  # noqa: F401
    CHAPTER_BRIDGE_PAYLOAD_VERSION,
    CHAPTER_TRANSITION_PAYLOAD_VERSION,
    LongformChapterRuntimeService,
    LongformChapterRuntimeServiceError,
    OUTLINE_PROGRESS_PAYLOAD_VERSION,
    PreparedChapterTransition,
)

warnings.warn(
    "rp.services.longform_chapter_runtime_service is deprecated and will be removed next release; "
    "use rp.services.writer.longform_chapter_runtime_service instead.",
    DeprecationWarning,
    stacklevel=2,
)
