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
from rp.agent_runtime.setup.executor import _ProviderStreamPayloadError
from rp.context_engineering.compaction import ContextCompactPromptFailure
from rp.services.memory.graph_extraction_service import _StructuredOutputInvalid
from rp.services.retrieval.ingestion_service import _AssetProcessingError
from rp.services.story.block_mutation_service import (
    MemoryBlockMutationUnsupportedError,
    MemoryBlockProposalNotFoundError,
    MemoryBlockTargetMismatchError,
)
from rp.services.story.runtime_controller import MemoryBlockHistoryUnsupportedError
from rp.services.memory.contract_registry import MemoryContractRegistryError
from rp.services.writer.worker_memory_service import WorkerMemoryPermissionError
from rp.tools.setup_tool_contracts import SetupToolContractError


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


def test_reparented_setup_tool_contract_error_keeps_tool_boundary_contract() -> None:
    exc = SetupToolContractError(
        code="invalid_input",
        message="bad arg",
        error_code="SETUP_TOOL_FAILED",
        retryable=True,
        details={"field": "x"},
    )

    assert isinstance(exc, ValueError)
    assert isinstance(exc, RPError)
    assert exc.code == "invalid_input"
    assert exc.error_code == "SETUP_TOOL_FAILED"
    assert exc.retryable is True
    assert exc.details == {"field": "x"}
    assert str(exc) == "bad arg"

    try:
        raise SetupToolContractError(
            code="invalid_input",
            message="bad arg",
            error_code="SETUP_TOOL_FAILED",
            retryable=True,
            details={"field": "x"},
        )
    except ValueError as caught_value_error:
        value_error = caught_value_error

    try:
        raise SetupToolContractError(
            code="invalid_input",
            message="bad arg",
            error_code="SETUP_TOOL_FAILED",
            retryable=True,
            details={"field": "x"},
        )
    except RPError as caught_rp_error:
        rp_error = caught_rp_error

    assert isinstance(value_error, SetupToolContractError)
    assert isinstance(rp_error, SetupToolContractError)


def test_reparented_runtime_error_block_errors_keep_legacy_behavior() -> None:
    exc = MemoryBlockProposalNotFoundError("x")

    assert isinstance(exc, RuntimeError)
    assert isinstance(exc, RPError)
    assert str(MemoryBlockProposalNotFoundError("not found: p1")) == "not found: p1"

    assert isinstance(MemoryBlockMutationUnsupportedError("x"), RuntimeError)
    assert isinstance(MemoryBlockMutationUnsupportedError("x"), RPError)
    assert isinstance(MemoryBlockTargetMismatchError("x"), RuntimeError)
    assert isinstance(MemoryBlockTargetMismatchError("x"), RPError)
    assert isinstance(MemoryBlockHistoryUnsupportedError("x"), RuntimeError)
    assert isinstance(MemoryBlockHistoryUnsupportedError("x"), RPError)

    try:
        raise MemoryBlockProposalNotFoundError("not found: p1")
    except RuntimeError as caught_runtime_error:
        runtime_error = caught_runtime_error

    try:
        raise MemoryBlockProposalNotFoundError("not found: p1")
    except RPError as caught_rp_error:
        rp_error = caught_rp_error

    assert isinstance(runtime_error, MemoryBlockProposalNotFoundError)
    assert isinstance(rp_error, MemoryBlockProposalNotFoundError)


def test_reparented_internal_wrapper_errors_keep_legacy_behavior() -> None:
    stream_error = _ProviderStreamPayloadError("bad json")
    structured_error = _StructuredOutputInvalid("bad output")
    asset_error = _AssetProcessingError(
        "bad asset",
        warnings=["w1"],
        parse_status="failed",
    )
    compaction_error = ContextCompactPromptFailure("model_output_not_json")

    assert isinstance(stream_error, ValueError)
    assert isinstance(stream_error, RPError)
    assert str(stream_error) == "bad json"

    assert isinstance(structured_error, ValueError)
    assert isinstance(structured_error, RPError)
    assert str(structured_error) == "bad output"

    assert isinstance(asset_error, Exception)
    assert isinstance(asset_error, RPError)
    assert str(asset_error) == "bad asset"
    assert asset_error.warnings == ["w1"]
    assert asset_error.parse_status == "failed"

    assert isinstance(compaction_error, Exception)
    assert isinstance(compaction_error, RPError)
    assert str(compaction_error) == "model_output_not_json"
    assert compaction_error.reason == "model_output_not_json"
