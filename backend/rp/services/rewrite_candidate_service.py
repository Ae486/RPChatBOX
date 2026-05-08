"""Persist rewrite candidates and deterministic paragraph patch previews."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.revision_overlay_contracts import (
    DraftDocumentRecord,
    ParagraphRewritePatch,
    ReplacementBlock,
    RewriteCandidateRecord,
    RewriteRequest,
)
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.writing_worker_contracts import WritingWorkerExecutionResult
from rp.services.revision_overlay_service import RevisionOverlayService
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService


REWRITE_CANDIDATE_PAYLOAD_VERSION = "rewrite-candidate.v1"
_REWRITE_CANDIDATE_DOMAIN = "chapter"


class RewriteCandidateServiceError(ValueError):
    """Stable rewrite candidate service error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class RewriteCandidateService:
    """Create and list Runtime Workspace rewrite candidates without adoption."""

    def __init__(
        self,
        *,
        revision_overlay_service: RevisionOverlayService | None = None,
        workspace_material_service: RuntimeWorkspaceMaterialService | None = None,
        session: Session | None = None,
    ) -> None:
        self._workspace_material_service = (
            workspace_material_service
            if workspace_material_service is not None
            else RuntimeWorkspaceMaterialService(session=session)
        )
        self._revision_overlay_service = (
            revision_overlay_service
            if revision_overlay_service is not None
            else RevisionOverlayService(
                workspace_material_service=self._workspace_material_service,
                session=session,
            )
        )

    def create_full_rewrite_candidate(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        rewrite_request: RewriteRequest,
        writer_result: WritingWorkerExecutionResult,
    ) -> RewriteCandidateRecord:
        self._require_request(
            identity=identity,
            rewrite_request=rewrite_request,
            rewrite_scope="full",
        )
        self._require_rewrite_writer_result(writer_result)
        full_output_text = _require_non_blank(
            writer_result.output_text,
            field_name="output_text",
        )
        candidate = self._build_candidate(
            identity=identity,
            rewrite_request=rewrite_request,
            candidate_output_ref=(
                writer_result.candidate_output_ref
                or f"rewrite_candidate_{uuid4().hex}"
            ),
            full_output_text=full_output_text,
            candidate_draft_text=full_output_text,
            paragraph_patch=None,
            target_block_ids=[],
            source_ref_ids=_candidate_source_ref_ids(
                rewrite_request=rewrite_request,
                extra_refs=[writer_result.request_id, writer_result.packet_id],
            ),
            metadata_json={
                "writer_result_request_id": writer_result.request_id,
                "packet_id": writer_result.packet_id,
                "output_kind": writer_result.output_kind,
                "writer_output_material_id": writer_result.writer_output_material_id,
            },
        )
        self._record_candidate(identity=identity, candidate=candidate)
        return candidate

    def create_paragraph_rewrite_candidate(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        rewrite_request: RewriteRequest,
        replacement_blocks: list[ReplacementBlock],
        writer_result: WritingWorkerExecutionResult | None = None,
    ) -> RewriteCandidateRecord:
        self._require_request(
            identity=identity,
            rewrite_request=rewrite_request,
            rewrite_scope="paragraph",
        )
        if writer_result is not None:
            self._require_rewrite_writer_result(writer_result)
        normalized_replacements = _require_replacement_blocks(replacement_blocks)
        draft = self._require_draft(identity=identity, rewrite_request=rewrite_request)
        self._require_patch_targets(
            rewrite_request=rewrite_request,
            replacement_blocks=normalized_replacements,
        )
        patch = ParagraphRewritePatch(
            draft_ref=rewrite_request.draft_ref,
            target_block_ids=list(rewrite_request.target_block_ids),
            replacement_blocks=normalized_replacements,
            touched_comment_ids=list(rewrite_request.comment_refs),
            metadata_json={
                "rewrite_request_id": rewrite_request.request_id,
                "target_range_ref": rewrite_request.target_range_ref,
                "patch_owner": "rp_runtime",
            },
        )
        candidate_draft_text = _compose_paragraph_candidate_text(
            draft=draft,
            replacement_blocks=normalized_replacements,
        )
        candidate = self._build_candidate(
            identity=identity,
            rewrite_request=rewrite_request,
            candidate_output_ref=(
                None
                if writer_result is None
                else writer_result.candidate_output_ref
            )
            or f"rewrite_candidate_{uuid4().hex}",
            full_output_text=None,
            candidate_draft_text=candidate_draft_text,
            paragraph_patch=patch,
            target_block_ids=list(rewrite_request.target_block_ids),
            source_ref_ids=_candidate_source_ref_ids(
                rewrite_request=rewrite_request,
                extra_refs=(
                    []
                    if writer_result is None
                    else [writer_result.request_id, writer_result.packet_id]
                ),
            ),
            metadata_json={
                "writer_result_request_id": (
                    None if writer_result is None else writer_result.request_id
                ),
                "packet_id": None if writer_result is None else writer_result.packet_id,
                "output_kind": None if writer_result is None else writer_result.output_kind,
                "writer_output_material_id": (
                    None
                    if writer_result is None
                    else writer_result.writer_output_material_id
                ),
            },
        )
        self._record_candidate(identity=identity, candidate=candidate)
        return candidate

    def list_candidates(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str | None = None,
        rewrite_scope: str | None = None,
    ) -> list[RewriteCandidateRecord]:
        normalized_draft_ref = (
            None
            if draft_ref is None
            else _require_non_blank(draft_ref, field_name="draft_ref")
        )
        normalized_scope = (
            None
            if rewrite_scope is None
            else _require_rewrite_scope(rewrite_scope)
        )
        candidates = [
            RewriteCandidateRecord.model_validate(material.payload.get("record"))
            for material in self._list_candidate_materials(identity=identity)
            if material.payload.get("payload_kind") == "rewrite_candidate"
        ]
        return [
            candidate
            for candidate in candidates
            if (
                normalized_draft_ref is None
                or candidate.draft_ref == normalized_draft_ref
            )
            and (
                normalized_scope is None
                or candidate.rewrite_scope == normalized_scope
            )
        ]

    def _require_request(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        rewrite_request: RewriteRequest,
        rewrite_scope: str,
    ) -> None:
        if rewrite_request.session_id != identity.session_id:
            raise RewriteCandidateServiceError(
                "revision_session_mismatch",
                rewrite_request.session_id,
            )
        if rewrite_request.turn_id != identity.turn_id:
            raise RewriteCandidateServiceError(
                "revision_turn_mismatch",
                rewrite_request.turn_id,
            )
        self._require_request_identity_metadata(
            identity=identity,
            rewrite_request=rewrite_request,
        )
        if rewrite_request.rewrite_scope != rewrite_scope:
            raise RewriteCandidateServiceError(
                "revision_rewrite_scope_mismatch",
                rewrite_request.rewrite_scope,
            )

    @staticmethod
    def _require_request_identity_metadata(
        *,
        identity: MemoryRuntimeIdentity,
        rewrite_request: RewriteRequest,
    ) -> None:
        expected = {
            "story_id": identity.story_id,
            "session_id": identity.session_id,
            "branch_head_id": identity.branch_head_id,
            "turn_id": identity.turn_id,
            "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
        }
        for field_name, expected_value in expected.items():
            actual = rewrite_request.metadata_json.get(field_name)
            if actual is None:
                raise RewriteCandidateServiceError(
                    "revision_runtime_identity_missing",
                    field_name,
                )
            if actual != expected_value:
                raise RewriteCandidateServiceError(
                    f"revision_{field_name}_mismatch",
                    str(actual),
                )

    def _require_rewrite_writer_result(
        self,
        writer_result: WritingWorkerExecutionResult,
    ) -> None:
        if writer_result.operation_mode != "rewrite":
            raise RewriteCandidateServiceError(
                "revision_writer_result_not_rewrite",
                writer_result.operation_mode,
            )
        if writer_result.result_status != "completed":
            raise RewriteCandidateServiceError(
                "revision_writer_result_not_completed",
                writer_result.result_status,
            )
        if writer_result.selected_output_ref is not None:
            raise RewriteCandidateServiceError(
                "revision_rewrite_auto_selection_forbidden",
                writer_result.selected_output_ref,
            )
        if writer_result.visible_output_ref is not None:
            raise RewriteCandidateServiceError(
                "revision_rewrite_visible_output_forbidden",
                writer_result.visible_output_ref,
            )

    def _require_draft(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        rewrite_request: RewriteRequest,
    ) -> DraftDocumentRecord:
        draft = self._revision_overlay_service.find_draft_document_by_ref(
            identity=identity,
            draft_ref=rewrite_request.draft_ref,
        )
        if draft is None:
            raise RewriteCandidateServiceError(
                "revision_draft_not_visible",
                rewrite_request.draft_ref,
            )
        if draft.draft_document_id != rewrite_request.draft_document_id:
            raise RewriteCandidateServiceError(
                "revision_draft_document_mismatch",
                rewrite_request.draft_document_id,
            )
        return draft

    def _require_patch_targets(
        self,
        *,
        rewrite_request: RewriteRequest,
        replacement_blocks: list[ReplacementBlock],
    ) -> None:
        target_ids = list(rewrite_request.target_block_ids)
        replacement_ids = [block.block_id for block in replacement_blocks]
        if not target_ids:
            raise RewriteCandidateServiceError(
                "revision_target_blocks_required",
                rewrite_request.request_id,
            )
        if set(replacement_ids) != set(target_ids):
            raise RewriteCandidateServiceError(
                "revision_replacement_block_target_mismatch",
                ",".join(replacement_ids),
            )

    def _build_candidate(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        rewrite_request: RewriteRequest,
        candidate_output_ref: str,
        full_output_text: str | None,
        candidate_draft_text: str | None,
        paragraph_patch: ParagraphRewritePatch | None,
        target_block_ids: list[str],
        source_ref_ids: list[str],
        metadata_json: dict[str, object],
    ) -> RewriteCandidateRecord:
        normalized_candidate_ref = _require_non_blank(
            candidate_output_ref,
            field_name="candidate_output_ref",
        )
        return RewriteCandidateRecord(
            candidate_id=normalized_candidate_ref,
            candidate_output_ref=normalized_candidate_ref,
            session_id=identity.session_id,
            turn_id=identity.turn_id,
            draft_ref=rewrite_request.draft_ref,
            draft_document_id=rewrite_request.draft_document_id,
            rewrite_request_id=rewrite_request.request_id,
            rewrite_scope=rewrite_request.rewrite_scope,
            full_output_text=full_output_text,
            candidate_draft_text=candidate_draft_text,
            paragraph_patch=paragraph_patch,
            target_block_ids=target_block_ids,
            touched_comment_ids=list(rewrite_request.comment_refs),
            touched_tracked_change_ids=list(rewrite_request.tracked_change_refs),
            source_ref_ids=source_ref_ids,
            selected_output_ref=None,
            adopted_output_ref=None,
            canonical_truth=False,
            created_at=datetime.now(timezone.utc),
            metadata_json={
                "payload_version": REWRITE_CANDIDATE_PAYLOAD_VERSION,
                "request_owner": "rp_runtime",
                "candidate_owner": "rp_runtime",
                "runtime_truth_owner": "rp_runtime",
                "superdoc_truth_owner": False,
                "canonical_truth": False,
                "selected_output_ref": None,
                "adopted_output_ref": None,
                **_identity_metadata(identity),
                **metadata_json,
            },
        )

    def _record_candidate(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        candidate: RewriteCandidateRecord,
    ) -> None:
        source_refs = [
            MemorySourceRef(
                source_type="rewrite_request",
                source_id=candidate.rewrite_request_id,
                layer="runtime_workspace",
                domain=_REWRITE_CANDIDATE_DOMAIN,
                block_id="chapter.runtime_workspace",
                entry_id=candidate.candidate_id,
                metadata={
                    "draft_ref": candidate.draft_ref,
                    "draft_document_id": candidate.draft_document_id,
                    "candidate_output_ref": candidate.candidate_output_ref,
                },
            )
        ]
        self._workspace_material_service.record_material(
            RuntimeWorkspaceMaterial(
                material_id=f"rewrite_candidate_{candidate.candidate_id}",
                material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
                identity=identity,
                domain=_REWRITE_CANDIDATE_DOMAIN,
                domain_path="chapter.revision_overlay.rewrite_candidate",
                source_refs=source_refs,
                payload={
                    "payload_version": REWRITE_CANDIDATE_PAYLOAD_VERSION,
                    "payload_kind": "rewrite_candidate",
                    "record_id": candidate.candidate_id,
                    "record": candidate.model_dump(mode="json"),
                    "runtime_truth_owner": "rp_runtime",
                    "superdoc_truth_owner": False,
                    "canonical_truth": False,
                    "selected_output_ref": None,
                    "adopted_output_ref": None,
                },
                visibility=RuntimeWorkspaceMaterialVisibility.REVIEW_VISIBLE.value,
                created_by="revision_overlay.rewrite_candidate",
                metadata={
                    "revision_overlay_candidate": True,
                    "runtime_truth_owner": "rp_runtime",
                    "superdoc_truth_owner": False,
                    "canonical_truth": False,
                    "selected_output_ref": None,
                    "adopted_output_ref": None,
                },
            )
        )

    def _list_candidate_materials(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> list[RuntimeWorkspaceMaterial]:
        return [
            material
            for material in self._workspace_material_service.list_materials(
                identity=identity,
                material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
                domain=_REWRITE_CANDIDATE_DOMAIN,
                lifecycle=RuntimeWorkspaceMaterialLifecycle.ACTIVE,
            )
            if material.payload.get("payload_version")
            == REWRITE_CANDIDATE_PAYLOAD_VERSION
        ]


def _require_replacement_blocks(
    replacement_blocks: list[ReplacementBlock],
) -> list[ReplacementBlock]:
    if not replacement_blocks:
        raise RewriteCandidateServiceError(
            "revision_replacement_blocks_required",
            "replacement_blocks",
        )
    normalized = list(replacement_blocks)
    replacement_ids = [block.block_id for block in normalized]
    if len(set(replacement_ids)) != len(replacement_ids):
        raise RewriteCandidateServiceError(
            "revision_replacement_block_target_mismatch",
            ",".join(replacement_ids),
        )
    return normalized


def _compose_paragraph_candidate_text(
    *,
    draft: DraftDocumentRecord,
    replacement_blocks: list[ReplacementBlock],
) -> str:
    replacement_by_id = {block.block_id: block for block in replacement_blocks}
    candidate_blocks = []
    for block in sorted(draft.blocks, key=lambda item: item.order):
        replacement = replacement_by_id.get(block.block_id)
        candidate_blocks.append(
            replacement.replacement_text if replacement is not None else block.text
        )
    return "\n\n".join(candidate_blocks)


def _candidate_source_ref_ids(
    *,
    rewrite_request: RewriteRequest,
    extra_refs: list[str],
) -> list[str]:
    refs = [
        f"draft_document:{rewrite_request.draft_document_id}",
        f"rewrite_request:{rewrite_request.request_id}",
        *[f"draft_block:{block_id}" for block_id in rewrite_request.target_block_ids],
        *[f"revision_comment:{comment_id}" for comment_id in rewrite_request.comment_refs],
        *[
            f"tracked_change:{tracked_change_id}"
            for tracked_change_id in rewrite_request.tracked_change_refs
        ],
        *[f"writer_result:{ref}" for ref in extra_refs if str(ref or "").strip()],
    ]
    return _dedupe_refs(refs)


def _identity_metadata(identity: MemoryRuntimeIdentity) -> dict[str, str]:
    return {
        "story_id": identity.story_id,
        "session_id": identity.session_id,
        "branch_head_id": identity.branch_head_id,
        "turn_id": identity.turn_id,
        "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
    }


def _require_rewrite_scope(value: str) -> str:
    normalized = _require_non_blank(value, field_name="rewrite_scope")
    if normalized not in {"full", "paragraph"}:
        raise RewriteCandidateServiceError(
            "revision_rewrite_scope_mismatch",
            normalized,
        )
    return normalized


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise RewriteCandidateServiceError(
            "revision_required_field_missing",
            field_name,
        )
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
