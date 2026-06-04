"""Shared RP business error hierarchy."""

from __future__ import annotations

from typing import Any


class RPError(Exception):
    """Base for RP business errors with machine-readable error metadata."""

    code: str = ""
    detail: str | None = None
    retryable: bool = False
    details: dict[str, Any] | None = None

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        detail: str | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if detail is not None:
            self.detail = detail
        self.retryable = retryable
        self.details = details


class RPValidationError(RPError, ValueError):
    pass


class RPNotFoundError(RPError, ValueError):
    pass


class RPConflictError(RPError, ValueError):
    pass


class RPConfigError(RPError, ValueError):
    pass


class RPStateError(RPError, RuntimeError):
    pass


class RPUpstreamError(RPError, RuntimeError):
    pass
