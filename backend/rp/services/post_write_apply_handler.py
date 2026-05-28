"""DEPRECATED: moved to rp.services.proposal.post_write_apply_handler."""
from __future__ import annotations

import warnings

from rp.services.proposal.post_write_apply_handler import *  # noqa: F401, F403
from rp.services.proposal.post_write_apply_handler import (  # noqa: F401
    PostWriteApplyHandler,
)

warnings.warn(
    "rp.services.post_write_apply_handler is deprecated and will be removed next release; "
    "use rp.services.proposal.post_write_apply_handler instead.",
    DeprecationWarning,
    stacklevel=2,
)
