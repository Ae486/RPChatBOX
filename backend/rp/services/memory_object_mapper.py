"""DEPRECATED: moved to rp.services.memory.object_mapper."""
from __future__ import annotations

import warnings

from rp.services.memory.object_mapper import *  # noqa: F401, F403
from rp.services.memory.object_mapper import (  # noqa: F401
    AuthoritativeBinding,
    ProjectionBinding,
    authoritative_bindings,
    default_authoritative_ref_for_domain,
    normalize_authoritative_ref,
    normalize_projection_summary_id,
    projection_bindings,
    projection_summary_ids_for_domain,
    resolve_authoritative_binding,
    resolve_projection_binding,
)

warnings.warn(
    "rp.services.memory_object_mapper is deprecated and will be removed next release; "
    "use rp.services.memory.object_mapper instead.",
    DeprecationWarning,
    stacklevel=2,
)
