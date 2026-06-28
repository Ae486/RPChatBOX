"""Stable writer-retrieval error for the graph-harness writer path.

INPUT: a machine-readable error code and detail at the writer retrieval boundary.
OUTPUT: a typed RPError/ValueError carrying the stable code.
POS: writer-zone retrieval error contract; relocated from the deleted bounded loop service.
"""

from __future__ import annotations

from rp.errors import RPError
from rp.models.retrieval.runtime_contracts import RetrievalFailureCategory


class WriterRetrievalError(RPError, ValueError):
    """Stable writer-retrieval error with a machine-readable code.

    ``code`` keeps the specific sub-reason (provider tool error code / harness
    finish reason); ``category`` carries the RET-013 normalized taxonomy axis so
    a retrieval-tool failure stays distinguishable from a model failure.
    """

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        category: RetrievalFailureCategory | None = None,
    ):
        self.code = code
        self.category = category
        super().__init__(f"{code}:{detail}")
