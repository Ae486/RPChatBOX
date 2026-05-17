"""Compact artifact reuse/update/rebuild/fallback mechanics."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Protocol

from rp.context_engineering.contracts import (
    ContextArtifact,
    ContextCompactPromptRequest,
    ContextFallbackReport,
    ContextOperationRequest,
    ContextOperationResult,
    ContextReadManifest,
    ContextSourceItem,
    ContextValidationIssue,
    ContextValidationReport,
)
from rp.context_engineering.fingerprinting import (
    fingerprint_source_items,
    is_valid_prefix_artifact,
)
from rp.context_engineering.serialization import serialize_source_item_content
from rp.context_engineering.tracing import build_manifest_item, build_trace
from rp.context_engineering.validation import (
    filter_allowed_recovery_refs,
    validate_payload_against_policy,
)

CompactionAction = Literal["not_needed", "reused", "updated", "rebuilt"]


class CompactPromptRunner(Protocol):
    """Injected no-tools compact prompt runner."""

    async def run_compact_prompt(
        self,
        request: ContextCompactPromptRequest,
    ) -> dict[str, Any]: ...


def decide_compaction_action(
    *,
    dropped_items: Sequence[ContextSourceItem],
    previous_artifact: ContextArtifact | None,
) -> CompactionAction:
    """Choose reuse/update/rebuild based only on dropped source fingerprints."""

    if not dropped_items:
        return "not_needed"
    if previous_artifact is None:
        return "rebuilt"
    if not previous_artifact.validation_report.valid:
        return "rebuilt"
    fingerprint = fingerprint_source_items(dropped_items)
    if (
        previous_artifact.source_fingerprint == fingerprint
        and previous_artifact.source_item_count == len(dropped_items)
    ):
        return "reused"
    if is_valid_prefix_artifact(
        previous_artifact=previous_artifact,
        dropped_items=dropped_items,
    ):
        return "updated"
    return "rebuilt"


async def run_compact_operation(
    *,
    request: ContextOperationRequest,
    dropped_items: Sequence[ContextSourceItem],
    first_kept_source_item_id: str | None,
    compact_prompt_runner: CompactPromptRunner | None = None,
) -> ContextOperationResult:
    """Run a compact operation with deterministic fallback options."""

    dropped = list(dropped_items)
    action = decide_compaction_action(
        dropped_items=dropped,
        previous_artifact=request.previous_artifact,
    )
    manifest = _manifest_for_dropped(dropped)
    empty_report = ContextValidationReport(valid=True)

    if action == "not_needed":
        return _operation_result(
            request=request,
            status="not_needed",
            dropped_items=dropped,
            manifest=manifest,
            validation_report=empty_report,
            artifact=None,
            fallback_report=None,
            summary_action="not_needed",
        )

    if action == "reused" and request.previous_artifact is not None:
        return _operation_result(
            request=request,
            status="reused",
            dropped_items=dropped,
            manifest=manifest,
            validation_report=request.previous_artifact.validation_report,
            artifact=request.previous_artifact,
            fallback_report=None,
            summary_action="reused",
        )

    fingerprint = fingerprint_source_items(dropped)
    prompt_items = _prompt_items_for_action(
        action=action,
        dropped=dropped,
        previous_artifact=request.previous_artifact,
    )
    if compact_prompt_runner is not None:
        prompt_request = ContextCompactPromptRequest(
            operation_id=request.operation_id,
            action=action,  # type: ignore[arg-type]
            schema_id=request.validation_policy.schema_id,
            source_fingerprint=fingerprint,
            source_item_count=len(dropped),
            dropped_items=prompt_items,
            previous_artifact_payload=(
                request.previous_artifact.payload
                if action == "updated" and request.previous_artifact is not None
                else None
            ),
            first_kept_source_item_id=first_kept_source_item_id,
            validation_policy=request.validation_policy,
            fallback_policy=request.fallback_policy,
            metadata=dict(request.metadata),
        )
        try:
            payload = await compact_prompt_runner.run_compact_prompt(prompt_request)
            artifact = _artifact_from_model_payload(
                request=request,
                payload=payload,
                source_fingerprint=fingerprint,
                source_item_count=len(dropped),
                first_kept_source_item_id=first_kept_source_item_id,
            )
            if artifact.validation_report.valid:
                return _operation_result(
                    request=request,
                    status=action,
                    dropped_items=dropped,
                    manifest=manifest,
                    validation_report=artifact.validation_report,
                    artifact=artifact,
                    fallback_report=None,
                    summary_action=action,
                )
            return _fallback_result(
                request=request,
                dropped_items=dropped,
                manifest=manifest,
                fingerprint=fingerprint,
                first_kept_source_item_id=first_kept_source_item_id,
                reason=_issue_reason(artifact.validation_report),
                summary_action=action,
            )
        except Exception as exc:
            return _fallback_result(
                request=request,
                dropped_items=dropped,
                manifest=manifest,
                fingerprint=fingerprint,
                first_kept_source_item_id=first_kept_source_item_id,
                reason=str(exc) or exc.__class__.__name__,
                summary_action=action,
            )

    return _fallback_result(
        request=request,
        dropped_items=dropped,
        manifest=manifest,
        fingerprint=fingerprint,
        first_kept_source_item_id=first_kept_source_item_id,
        reason="compact_prompt_runner_unavailable",
        summary_action=action,
    )


def _prompt_items_for_action(
    *,
    action: CompactionAction,
    dropped: list[ContextSourceItem],
    previous_artifact: ContextArtifact | None,
) -> list[ContextSourceItem]:
    if action == "updated" and previous_artifact is not None:
        return list(dropped[int(previous_artifact.source_item_count) :])
    return list(dropped)


def _artifact_from_model_payload(
    *,
    request: ContextOperationRequest,
    payload: dict[str, Any],
    source_fingerprint: str,
    source_item_count: int,
    first_kept_source_item_id: str | None,
) -> ContextArtifact:
    validation_issues: list[ContextValidationIssue] = []
    normalized = dict(payload)
    if (
        normalized.get("source_fingerprint") is not None
        and normalized.get("source_fingerprint") != source_fingerprint
    ):
        validation_issues.append(
            ContextValidationIssue(
                code="source_fingerprint_mismatch",
                message="Compact payload source_fingerprint does not match dropped sources.",
                field_path="source_fingerprint",
            )
        )
    source_message_count_value = normalized.get("source_message_count")
    if source_message_count_value is not None:
        try:
            count_matches = int(source_message_count_value) == source_item_count
        except (TypeError, ValueError):
            count_matches = False
        if not count_matches:
            validation_issues.append(
                ContextValidationIssue(
                    code="source_message_count_mismatch",
                    message="Compact payload source_message_count does not match dropped sources.",
                    field_path="source_message_count",
                )
            )
    normalized["source_fingerprint"] = source_fingerprint
    normalized["source_message_count"] = source_item_count
    report = validate_payload_against_policy(
        payload=normalized,
        policy=request.validation_policy,
    )
    if validation_issues:
        report = ContextValidationReport(
            valid=False,
            issues=[*validation_issues, *report.issues],
        )
    return ContextArtifact(
        artifact_id=f"{request.operation_id}:compact:{source_fingerprint[:12]}",
        artifact_kind="compact_summary",
        schema_id=request.validation_policy.schema_id or "context.compact.v1",
        schema_version="1",
        source_fingerprint=source_fingerprint,
        source_item_count=source_item_count,
        payload=normalized,
        recovery_refs=_payload_recovery_refs(normalized),
        first_kept_source_item_id=first_kept_source_item_id,
        created_by="model",
        validation_report=report,
    )


def _fallback_result(
    *,
    request: ContextOperationRequest,
    dropped_items: list[ContextSourceItem],
    manifest: ContextReadManifest,
    fingerprint: str,
    first_kept_source_item_id: str | None,
    reason: str,
    summary_action: str,
) -> ContextOperationResult:
    fallback_report = ContextFallbackReport(
        mode=request.fallback_policy.mode,
        reason=reason[:240],
        user_visible_error_code=request.fallback_policy.user_visible_error_code,
    )
    if request.fallback_policy.mode == "fail_closed":
        return _operation_result(
            request=request,
            status="failed",
            dropped_items=dropped_items,
            manifest=manifest,
            validation_report=ContextValidationReport(
                valid=False,
                issues=[
                    ContextValidationIssue(
                        code="compact_operation_failed_closed",
                        message=reason[:240],
                    )
                ],
            ),
            artifact=None,
            fallback_report=fallback_report,
            summary_action=summary_action,
            fallback_reason=reason[:240],
        )
    if request.fallback_policy.mode == "skip_section":
        return _operation_result(
            request=request,
            status="fallback",
            dropped_items=dropped_items,
            manifest=manifest,
            validation_report=ContextValidationReport(valid=True),
            artifact=None,
            fallback_report=fallback_report,
            summary_action=summary_action,
            fallback_reason=reason[:240],
        )
    payload, recovery_refs = _deterministic_payload(
        request=request,
        dropped_items=dropped_items,
        fingerprint=fingerprint,
    )
    report = validate_payload_against_policy(
        payload=payload,
        policy=request.validation_policy,
    )
    artifact = ContextArtifact(
        artifact_id=f"{request.operation_id}:fallback:{fingerprint[:12]}",
        artifact_kind="compact_summary",
        schema_id=request.validation_policy.schema_id or "context.compact.v1",
        schema_version="1",
        source_fingerprint=fingerprint,
        source_item_count=len(dropped_items),
        payload=payload,
        recovery_refs=recovery_refs,
        first_kept_source_item_id=first_kept_source_item_id,
        created_by="deterministic",
        validation_report=report,
        fallback_report=fallback_report,
    )
    return _operation_result(
        request=request,
        status="fallback",
        dropped_items=dropped_items,
        manifest=manifest,
        validation_report=report,
        artifact=artifact,
        fallback_report=fallback_report,
        summary_action=summary_action,
        fallback_reason=reason[:240],
    )


def _deterministic_payload(
    *,
    request: ContextOperationRequest,
    dropped_items: Sequence[ContextSourceItem],
    fingerprint: str,
) -> tuple[dict[str, Any], list[str]]:
    allowed_fields = request.validation_policy.metadata.get("allowed_payload_fields")
    allowed_set = (
        {str(field) for field in allowed_fields}
        if isinstance(allowed_fields, (list, tuple, set))
        else None
    )
    refs, _ = filter_allowed_recovery_refs(
        refs=[ref for item in dropped_items for ref in item.recovery_refs],
        policy=request.validation_policy,
    )
    payload: dict[str, Any] = {
        "source_fingerprint": fingerprint,
        "source_message_count": len(dropped_items),
    }
    lines = _fallback_lines(
        dropped_items,
        limit=request.fallback_policy.fallback_summary_line_limit,
    )
    _put_if_allowed(payload, allowed_set, "summary_lines", lines)
    _put_if_allowed(payload, allowed_set, "recovery_refs", refs)
    _put_if_allowed(payload, allowed_set, "draft_refs", refs)
    _put_if_allowed(
        payload,
        allowed_set,
        "recovery_hints",
        [
            {
                "ref": ref,
                "reason": "recover_exact_source_detail",
                "detail": None,
            }
            for ref in refs
        ],
    )
    for field in (
        "confirmed_points",
        "open_threads",
        "rejected_directions",
        "must_not_infer",
    ):
        _put_if_allowed(payload, allowed_set, field, [])
    if allowed_set is not None:
        payload = {key: value for key, value in payload.items() if key in allowed_set}
    return payload, refs


def _put_if_allowed(
    payload: dict[str, Any],
    allowed_set: set[str] | None,
    key: str,
    value: Any,
) -> None:
    if allowed_set is None or key in allowed_set:
        payload[key] = value


def _fallback_lines(
    dropped_items: Sequence[ContextSourceItem],
    *,
    limit: int,
) -> list[str]:
    lines: list[str] = []
    for item in dropped_items:
        text = serialize_source_item_content(item).strip()
        if not text:
            continue
        line = text[:240]
        if line not in lines:
            lines.append(line)
        if len(lines) >= int(limit):
            break
    return lines


def _operation_result(
    *,
    request: ContextOperationRequest,
    status: str,
    dropped_items: Sequence[ContextSourceItem],
    manifest: ContextReadManifest,
    validation_report: ContextValidationReport,
    artifact: ContextArtifact | None,
    fallback_report: ContextFallbackReport | None,
    summary_action: str,
    fallback_reason: str | None = None,
) -> ContextOperationResult:
    trace = build_trace(
        operation_id=request.operation_id,
        operation_kind=request.operation_kind,
        runtime_family=request.runtime_family,
        source_items=request.source_items,
        selected_items=[],
        read_manifest=manifest,
        summary_action=summary_action,
        fallback_reason=fallback_reason,
        provider_usage=dict((request.metadata or {}).get("provider_usage") or {}),
        metadata={
            **request.metadata,
            "dropped_source_count": len(dropped_items),
            "artifact_source_item_count": artifact.source_item_count if artifact else 0,
        },
    )
    return ContextOperationResult(
        operation_id=request.operation_id,
        status=status,  # type: ignore[arg-type]
        artifact=artifact,
        read_manifest=manifest,
        trace=trace,
        validation_report=validation_report,
        fallback_report=fallback_report,
    )


def _manifest_for_dropped(
    dropped_items: Sequence[ContextSourceItem],
) -> ContextReadManifest:
    manifest = ContextReadManifest()
    for item in dropped_items:
        manifest.omitted.append(
            build_manifest_item(
                item,
                decision="omitted",
                reason="compact_source",
            )
        )
    return manifest


def _payload_recovery_refs(payload: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for field in ("recovery_refs", "draft_refs"):
        value = payload.get(field)
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip()
                if text and text not in refs:
                    refs.append(text)
    hints = payload.get("recovery_hints")
    if isinstance(hints, list):
        for item in hints:
            if isinstance(item, dict):
                text = str(item.get("ref") or "").strip()
                if text and text not in refs:
                    refs.append(text)
    return refs


def _issue_reason(report: ContextValidationReport) -> str:
    if not report.issues:
        return "compact_payload_invalid"
    return ",".join(issue.code for issue in report.issues)[:240]
