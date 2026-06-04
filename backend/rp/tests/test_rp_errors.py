from __future__ import annotations

from rp.errors import (
    RPConfigError,
    RPConflictError,
    RPError,
    RPNotFoundError,
    RPStateError,
    RPUpstreamError,
    RPValidationError,
)
from rp.services.memory.contract_registry import MemoryContractRegistryError
from rp.services.writer.worker_memory_service import WorkerMemoryPermissionError


def test_semantic_error_classes_preserve_legacy_builtin_bases() -> None:
    assert isinstance(RPValidationError(), RPError)
    assert isinstance(RPValidationError(), ValueError)
    assert isinstance(RPNotFoundError(), ValueError)
    assert isinstance(RPConflictError(), ValueError)
    assert isinstance(RPConfigError(), ValueError)
    assert isinstance(RPStateError(), RPError)
    assert isinstance(RPStateError(), RuntimeError)
    assert isinstance(RPUpstreamError(), RuntimeError)


def test_rp_error_constructor_keeps_metadata_contract() -> None:
    exc = RPValidationError("msg", code="c", detail="d")

    assert exc.code == "c"
    assert exc.detail == "d"
    assert exc.retryable is False
    assert exc.details is None
    assert str(exc) == "msg"


def test_reparented_code_bearing_value_error_keeps_legacy_behavior() -> None:
    exc = MemoryContractRegistryError("not_found", "x")

    assert isinstance(exc, ValueError)
    assert isinstance(exc, RPError)
    assert exc.code == "not_found"
    assert str(exc) == "not_found:x"


def test_reparented_code_bearing_error_is_catchable_by_both_bases() -> None:
    try:
        raise MemoryContractRegistryError("not_found", "x")
    except ValueError as exc:
        value_error = exc

    try:
        raise MemoryContractRegistryError("not_found", "x")
    except RPError as exc:
        rp_error = exc

    assert isinstance(value_error, MemoryContractRegistryError)
    assert isinstance(rp_error, MemoryContractRegistryError)


def test_reparented_variant_signature_preserves_no_clobber_contract() -> None:
    exc = WorkerMemoryPermissionError("denied", "x", reason_codes=["scope"])

    assert isinstance(exc, ValueError)
    assert isinstance(exc, RPError)
    assert exc.code == "denied"
    assert exc.reason_codes == ["scope"]
    assert str(exc) == "denied:x"
