"""Build rewrite requests and review-overlay packet sidecars for WritingWorker."""

from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.revision_overlay_contracts import (
    DraftDocumentBlock,
    DraftDocumentRecord,
    RewriteRequest,
    RevisionCommentRecord,
    TrackedChangeRecord,
)
from rp.services.revision_overlay_service import (
    RevisionOverlayService,
)


class RewriteRequestBuilderServiceError(ValueError):
    """Stable rewrite request builder error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class RewriteRequestBuilderService:
    """Create rewrite requests and sidecar sections without running the writer."""

    def __init__(
        self,
        *,
        revision_overlay_service: RevisionOverlayService | None = None,
        session: Session | None = None,
    ) -> None:
        self._revision_overlay_service = (
            revision_overlay_service
            if revision_overlay_service is not None
            else RevisionOverlayService(session=session)
        )

    def build_full_rewrite_request(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str,
        global_instruction: str | None,
        comment_refs: list[str],
        tracked_change_refs: list[str],
        include_full_draft_text: bool | None = None,
    ) -> RewriteRequest:
        draft = self._require_draft(identity=identity, draft_ref=draft_ref)
        normalized_instruction = _normalize_optional_text(global_instruction)
        if normalized_instruction is None:
            if include_full_draft_text is False:
                raise RewriteRequestBuilderServiceError(
                    "revision_full_rewrite_old_text_required",
                    draft_ref,
                )
            should_include_full_text = True
        else:
            should_include_full_text = False if include_full_draft_text is None else include_full_draft_text
        if normalized_instruction is not None and should_include_full_text:
            raise RewriteRequestBuilderServiceError(
                "revision_full_rewrite_old_text_forbidden",
                draft_ref,
            )
        comments, tracked_changes = self._resolve_revision_records(
            identity=identity,
            draft=draft,
            comment_refs=comment_refs,
            tracked_change_refs=tracked_change_refs,
        )
        return RewriteRequest(
            request_id=f"rewrite_request_{uuid4().hex}",
            session_id=identity.session_id,
            turn_id=identity.turn_id,
            draft_ref=draft.draft_ref,
            draft_document_id=draft.draft_document_id,
            rewrite_scope="full",
            global_instruction=normalized_instruction,
            comment_refs=[comment.comment_id for comment in comments],
            tracked_change_refs=[
                tracked_change.tracked_change_id
                for tracked_change in tracked_changes
            ],
            include_full_draft_text=should_include_full_text,
            full_draft_text=(
                _draft_text_from_blocks(draft.blocks)
                if should_include_full_text
                else None
            ),
            anchor_refs=[
                *[comment.anchor_ref for comment in comments],
                *[tracked_change.anchor_ref for tracked_change in tracked_changes],
            ],
            comments=comments,
            tracked_changes=tracked_changes,
            metadata_json={
                "payload_version": "rewrite-request.v1",
                "request_owner": "rp_runtime",
                **_identity_metadata(identity),
                "writer_operation_mode": "rewrite",
                "rewrite_scope": "full",
                "include_full_draft_text": should_include_full_text,
                "candidate_output_ref": None,
                "adopted_output_ref": None,
                "selection_receipt_id": None,
                "canonical_truth": False,
                "source_ref_ids": _source_ref_ids(
                    draft=draft,
                    comments=comments,
                    tracked_changes=tracked_changes,
                    target_block_ids=[],
                ),
            },
        )

    def build_paragraph_rewrite_request(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str,
        target_block_ids: list[str],
        comment_refs: list[str],
        tracked_change_refs: list[str],
        global_instruction: str | None = None,
    ) -> RewriteRequest:
        draft = self._require_draft(identity=identity, draft_ref=draft_ref)
        normalized_target_block_ids = _normalize_ref_list(
            target_block_ids,
            field_name="target_block_ids",
        )
        if not normalized_target_block_ids:
            raise RewriteRequestBuilderServiceError(
                "revision_target_blocks_required",
                draft_ref,
            )
        target_blocks = self._require_contiguous_target_blocks(
            draft=draft,
            target_block_ids=normalized_target_block_ids,
        )
        comments, tracked_changes = self._resolve_revision_records(
            identity=identity,
            draft=draft,
            comment_refs=comment_refs,
            tracked_change_refs=tracked_change_refs,
        )
        self._require_records_within_target_scope(
            draft=draft,
            target_block_ids=normalized_target_block_ids,
            comments=comments,
            tracked_changes=tracked_changes,
        )
        return RewriteRequest(
            request_id=f"rewrite_request_{uuid4().hex}",
            session_id=identity.session_id,
            turn_id=identity.turn_id,
            draft_ref=draft.draft_ref,
            draft_document_id=draft.draft_document_id,
            rewrite_scope="paragraph",
            global_instruction=_normalize_optional_text(global_instruction),
            target_block_ids=normalized_target_block_ids,
            target_range_ref=_target_range_ref(target_blocks),
            comment_refs=[comment.comment_id for comment in comments],
            tracked_change_refs=[
                tracked_change.tracked_change_id
                for tracked_change in tracked_changes
            ],
            include_full_draft_text=True,
            full_draft_text=_draft_text_from_blocks(draft.blocks),
            anchor_refs=[
                *[comment.anchor_ref for comment in comments],
                *[tracked_change.anchor_ref for tracked_change in tracked_changes],
            ],
            comments=comments,
            tracked_changes=tracked_changes,
            metadata_json={
                "payload_version": "rewrite-request.v1",
                "request_owner": "rp_runtime",
                **_identity_metadata(identity),
                "writer_operation_mode": "rewrite",
                "rewrite_scope": "paragraph",
                "include_full_draft_text": True,
                "expected_writer_output_shape": "paragraph_rewrite_patch",
                "replacement_blocks_required": True,
                "candidate_output_ref": None,
                "adopted_output_ref": None,
                "selection_receipt_id": None,
                "canonical_truth": False,
                "source_ref_ids": _source_ref_ids(
                    draft=draft,
                    comments=comments,
                    tracked_changes=tracked_changes,
                    target_block_ids=normalized_target_block_ids,
                ),
            },
        )

    def build_review_overlay_sections(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        rewrite_request: RewriteRequest,
    ) -> list[dict[str, object]]:
        _require_request_identity(identity=identity, rewrite_request=rewrite_request)
        source_ref_ids = _source_ref_ids(
            draft=DraftDocumentRecord(
                draft_document_id=rewrite_request.draft_document_id,
                turn_id=rewrite_request.turn_id,
                draft_ref=rewrite_request.draft_ref,
                source_output_ref=rewrite_request.draft_ref,
                source_format="plain_text",
                materialization_version="rewrite-request.sidecar",
                created_at=identity_created_at_placeholder(),
            ),
            comments=rewrite_request.comments,
            tracked_changes=rewrite_request.tracked_changes,
            target_block_ids=rewrite_request.target_block_ids,
        )
        metadata_json = {
            "draft_ref": rewrite_request.draft_ref,
            "draft_document_id": rewrite_request.draft_document_id,
            "rewrite_scope": rewrite_request.rewrite_scope,
            "target_block_ids": list(rewrite_request.target_block_ids),
            "target_range_ref": (
                dict(rewrite_request.target_range_ref)
                if rewrite_request.target_range_ref is not None
                else None
            ),
            "comments": [
                comment.model_dump(mode="json")
                for comment in rewrite_request.comments
            ],
            "tracked_changes": [
                tracked_change.model_dump(mode="json")
                for tracked_change in rewrite_request.tracked_changes
            ],
            "selected_excerpt": _selected_excerpt(rewrite_request.comments),
            "anchor_refs": [
                anchor.model_dump(mode="json")
                for anchor in rewrite_request.anchor_refs
            ],
            "instruction_text": rewrite_request.global_instruction,
            "include_full_draft_text": rewrite_request.include_full_draft_text,
            "source_ref_ids": source_ref_ids,
            "expected_writer_output_shape": (
                "paragraph_rewrite_patch"
                if rewrite_request.rewrite_scope == "paragraph"
                else "full_rewrite_candidate"
            ),
            "candidate_output_ref": None,
            "adopted_output_ref": None,
            "canonical_truth": False,
            "runtime_truth_owner": "rp_runtime",
            "superdoc_truth_owner": False,
        }
        if rewrite_request.include_full_draft_text:
            metadata_json["full_draft_text"] = rewrite_request.full_draft_text
        return [
            {
                "section_id": (
                    f"review_overlay.{rewrite_request.rewrite_scope}."
                    f"{rewrite_request.request_id}"
                ),
                "label": "review_overlay",
                "source_kind": "review_overlay_rewrite_request",
                "source_ref_ids": source_ref_ids,
                "items": _section_items(rewrite_request),
                "metadata_json": metadata_json,
            }
        ]

    def _require_draft(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str,
    ) -> DraftDocumentRecord:
        normalized_draft_ref = _require_non_blank(draft_ref, field_name="draft_ref")
        draft = self._revision_overlay_service.find_draft_document_by_ref(
            identity=identity,
            draft_ref=normalized_draft_ref,
        )
        if draft is None:
            raise RewriteRequestBuilderServiceError(
                "revision_draft_not_visible",
                normalized_draft_ref,
            )
        if draft.turn_id != identity.turn_id:
            raise RewriteRequestBuilderServiceError(
                "revision_turn_mismatch",
                draft.turn_id,
            )
        return draft

    def _resolve_revision_records(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft: DraftDocumentRecord,
        comment_refs: list[str],
        tracked_change_refs: list[str],
    ) -> tuple[list[RevisionCommentRecord], list[TrackedChangeRecord]]:
        normalized_comment_refs = _normalize_ref_list(
            comment_refs,
            field_name="comment_refs",
        )
        normalized_tracked_change_refs = _normalize_ref_list(
            tracked_change_refs,
            field_name="tracked_change_refs",
        )
        if not normalized_comment_refs and not normalized_tracked_change_refs:
            return [], []
        overlay = self._revision_overlay_service.find_overlay_for_draft_ref(
            identity=identity,
            draft_ref=draft.draft_ref,
        )
        if overlay is None:
            raise RewriteRequestBuilderServiceError(
                "revision_comment_draft_mismatch",
                draft.draft_ref,
            )
        inspection = self._revision_overlay_service.inspect_overlay(
            identity=identity,
            overlay_id=overlay.overlay_id,
        )
        comments_by_id = {comment.comment_id: comment for comment in inspection.comments}
        tracked_changes_by_id = {
            tracked_change.tracked_change_id: tracked_change
            for tracked_change in inspection.tracked_changes
        }
        comments = []
        for comment_id in normalized_comment_refs:
            comment = comments_by_id.get(comment_id)
            if comment is None or comment.draft_ref != draft.draft_ref:
                raise RewriteRequestBuilderServiceError(
                    "revision_comment_draft_mismatch",
                    comment_id,
                )
            if comment.status != "active":
                raise RewriteRequestBuilderServiceError(
                    "revision_comment_not_active",
                    comment_id,
                )
            comments.append(comment)
        tracked_changes = []
        for tracked_change_id in normalized_tracked_change_refs:
            tracked_change = tracked_changes_by_id.get(tracked_change_id)
            if tracked_change is None or tracked_change.draft_ref != draft.draft_ref:
                raise RewriteRequestBuilderServiceError(
                    "revision_comment_draft_mismatch",
                    tracked_change_id,
                )
            if tracked_change.status != "active":
                raise RewriteRequestBuilderServiceError(
                    "revision_tracked_change_not_active",
                    tracked_change_id,
                )
            tracked_changes.append(tracked_change)
        return comments, tracked_changes

    @staticmethod
    def _require_contiguous_target_blocks(
        *,
        draft: DraftDocumentRecord,
        target_block_ids: list[str],
    ) -> list[DraftDocumentBlock]:
        blocks_by_id = {block.block_id: block for block in draft.blocks}
        missing = [
            block_id
            for block_id in target_block_ids
            if block_id not in blocks_by_id
        ]
        if missing:
            raise RewriteRequestBuilderServiceError(
                "revision_anchor_block_not_found",
                ",".join(missing),
            )
        target_blocks = [blocks_by_id[block_id] for block_id in target_block_ids]
        orders = sorted(block.order for block in target_blocks)
        if orders != list(range(orders[0], orders[-1] + 1)):
            raise RewriteRequestBuilderServiceError(
                "revision_batch_paragraph_rewrite_unsupported",
                ",".join(target_block_ids),
            )
        return sorted(target_blocks, key=lambda block: block.order)

    @staticmethod
    def _require_records_within_target_scope(
        *,
        draft: DraftDocumentRecord,
        target_block_ids: list[str],
        comments: list[RevisionCommentRecord],
        tracked_changes: list[TrackedChangeRecord],
    ) -> None:
        target_id_set = set(target_block_ids)
        all_block_ids = {block.block_id for block in draft.blocks}
        for record_id, anchor_ref in [
            *[
                (comment.comment_id, comment.anchor_ref)
                for comment in comments
            ],
            *[
                (tracked_change.tracked_change_id, tracked_change.anchor_ref)
                for tracked_change in tracked_changes
            ],
        ]:
            anchor_block_ids = set(anchor_ref.block_ids)
            is_whole_draft_context = (
                anchor_ref.metadata_json.get("rewrite_context_scope")
                == "whole_draft"
                or anchor_block_ids == all_block_ids
            )
            if not anchor_block_ids <= target_id_set and not is_whole_draft_context:
                raise RewriteRequestBuilderServiceError(
                    "revision_comment_draft_mismatch",
                    record_id,
                )


def identity_created_at_placeholder():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _identity_metadata(identity: MemoryRuntimeIdentity) -> dict[str, str]:
    return {
        "story_id": identity.story_id,
        "session_id": identity.session_id,
        "branch_head_id": identity.branch_head_id,
        "turn_id": identity.turn_id,
        "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
    }


def _require_request_identity(
    *,
    identity: MemoryRuntimeIdentity,
    rewrite_request: RewriteRequest,
) -> None:
    if rewrite_request.session_id != identity.session_id:
        raise RewriteRequestBuilderServiceError(
            "revision_session_mismatch",
            rewrite_request.session_id,
        )
    if rewrite_request.turn_id != identity.turn_id:
        raise RewriteRequestBuilderServiceError(
            "revision_turn_mismatch",
            rewrite_request.turn_id,
        )
    metadata = rewrite_request.metadata_json
    expected = _identity_metadata(identity)
    for field_name, expected_value in expected.items():
        actual = metadata.get(field_name)
        if actual is None:
            raise RewriteRequestBuilderServiceError(
                "revision_runtime_identity_missing",
                field_name,
            )
        if actual != expected_value:
            raise RewriteRequestBuilderServiceError(
                f"revision_{field_name}_mismatch",
                str(actual),
            )


def _target_range_ref(blocks: list[DraftDocumentBlock]) -> dict[str, int] | None:
    ranges = [block.source_range for block in blocks if block.source_range is not None]
    if not ranges:
        return None
    return {
        "start": min(item["start"] for item in ranges),
        "end": max(item["end"] for item in ranges),
    }


def _draft_text_from_blocks(blocks: list[DraftDocumentBlock]) -> str:
    return "\n\n".join(block.text for block in sorted(blocks, key=lambda item: item.order))


def _source_ref_ids(
    *,
    draft: DraftDocumentRecord,
    comments: list[RevisionCommentRecord],
    tracked_changes: list[TrackedChangeRecord],
    target_block_ids: list[str],
) -> list[str]:
    refs = [
        f"draft_document:{draft.draft_document_id}",
        *[f"draft_block:{block_id}" for block_id in target_block_ids],
        *[f"revision_comment:{comment.comment_id}" for comment in comments],
        *[
            f"tracked_change:{tracked_change.tracked_change_id}"
            for tracked_change in tracked_changes
        ],
    ]
    return _dedupe_refs(refs)


def _section_items(rewrite_request: RewriteRequest) -> list[str]:
    items = [
        f"rewrite_scope: {rewrite_request.rewrite_scope}",
        f"draft_ref: {rewrite_request.draft_ref}",
    ]
    if rewrite_request.global_instruction is not None:
        items.append(f"global_instruction: {rewrite_request.global_instruction}")
    if rewrite_request.target_block_ids:
        items.append("target_block_ids: " + ", ".join(rewrite_request.target_block_ids))
    for comment in rewrite_request.comments:
        items.append(
            f"comment {comment.comment_id}: {comment.instruction_text}"
        )
    for tracked_change in rewrite_request.tracked_changes:
        change_parts = [
            f"tracked_change {tracked_change.tracked_change_id}",
            f"kind={tracked_change.change_kind}",
        ]
        if tracked_change.original_text:
            change_parts.append(f"original={tracked_change.original_text}")
        if tracked_change.suggested_text:
            change_parts.append(f"suggested={tracked_change.suggested_text}")
        items.append("; ".join(change_parts))
    if rewrite_request.rewrite_scope == "paragraph":
        items.append("writer_output_required: replacement_blocks")
    return items


def _selected_excerpt(comments: list[RevisionCommentRecord]) -> str | None:
    excerpts = [
        comment.selected_excerpt
        for comment in comments
        if comment.selected_excerpt is not None
    ]
    return "\n".join(excerpts) if excerpts else None


def _normalize_ref_list(values: list[str], *, field_name: str) -> list[str]:
    return [_require_non_blank(value, field_name=field_name) for value in values]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _dedupe_refs(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for ref in refs:
        key = ref.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(ref)
    return output
