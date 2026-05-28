"""DEPRECATED: moved to rp.services.story.chapter_bridge_provider."""
from __future__ import annotations

import warnings

from rp.services.story.chapter_bridge_provider import *  # noqa: F401, F403
from rp.services.story.chapter_bridge_provider import ChapterBridgeSummaryPayload, ChapterBridgeProvider  # noqa: F401

warnings.warn(
    "rp.services.chapter_bridge_provider is deprecated and will be removed next release; "
    "use rp.services.story.chapter_bridge_provider instead.",
    DeprecationWarning,
    stacklevel=2,
)
