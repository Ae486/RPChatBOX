"""Stable writer-retrieval error for the graph-harness writer path.

INPUT: a machine-readable error code and detail at the writer retrieval boundary.
OUTPUT: a typed RPError/ValueError carrying the stable code.
POS: writer-zone retrieval error contract; relocated from the deleted bounded loop service.
"""

from __future__ import annotations

from rp.errors import RPError


class WriterRetrievalError(RPError, ValueError):
    """Stable writer-retrieval error with a machine-readable code.

    ``code`` keeps the specific sub-reason (provider tool error code / harness
    finish reason) that production surfaces at the writer retrieval boundary.
    """

    def __init__(
        self,
        code: str,
        detail: str,
    ):
        self.code = code
        super().__init__(f"{code}:{detail}")
