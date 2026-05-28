"""DEPRECATED: moved to rp.services.core_state.legacy_state_patch_proposal_builder."""
from __future__ import annotations

import warnings

from rp.services.core_state.legacy_state_patch_proposal_builder import *  # noqa: F401, F403
from rp.services.core_state.legacy_state_patch_proposal_builder import LegacyStatePatchProposalBuilder  # noqa: F401

warnings.warn(
    "rp.services.legacy_state_patch_proposal_builder is deprecated and will be removed next release; "
    "use rp.services.core_state.legacy_state_patch_proposal_builder instead.",
    DeprecationWarning,
    stacklevel=2,
)
