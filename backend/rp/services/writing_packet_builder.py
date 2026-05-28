"""DEPRECATED: moved to rp.services.writer.writing_packet_builder."""
from __future__ import annotations

import warnings

from rp.services.writer.writing_packet_builder import *  # noqa: F401, F403
from rp.services.writer.writing_packet_builder import WritingPacketBuilder  # noqa: F401

warnings.warn(
    "rp.services.writing_packet_builder is deprecated and will be removed next release; "
    "use rp.services.writer.writing_packet_builder instead.",
    DeprecationWarning,
    stacklevel=2,
)
