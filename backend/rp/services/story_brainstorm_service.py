"""Writer brainstorm session, discussion, summarize, and Stage W batch service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from models.chat import ChatMessage
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.story_brainstorm import (
    BrainstormBatch,
    BrainstormBatchItem,
    BrainstormBatchStatus,
    BrainstormBatchSubmitReceipt,
    BrainstormBatchSubmitRequest,
    BrainstormContextFlushReason,
    BrainstormContextWindow,
    BrainstormContextWindowStatus,
    BrainstormContinueWritingRequest,
    BrainstormDiscussionRequest,
    BrainstormItemCreateRequest,
    BrainstormItemSourceKind,
    BrainstormItemStatus,
    BrainstormItemUpdateRequest,
    BrainstormMessage,
    BrainstormSession,
    BrainstormSessionStartRequest,
    BrainstormSessionStatus,
    BrainstormSummarizeOutput,
    BrainstormSummarizeRequest,
)
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
    RuntimeWorkspaceMaterialServiceError,
)
from rp.services.story_llm_gateway import StoryLlmGateway
from rp.services.story_session_service import StorySessionService


BRAINSTORM_MATERIAL_DOMAIN = "narrative_progress"
BRAINSTORM_MATERIAL_DOMAIN_PATH = "narrative_progress.runtime.brainstorm"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _ChapterBrainstormContext:
    phase: str
    outline_text: str
    accepted_segments: list[str]
    current_title: str


class StoryBrainstormServiceError(ValueError):
    """Stable brainstorm service error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class StoryBrainstormService:
    """Persist brainstorm scratch and Stage W batch review state in Runtime Workspace."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        runtime_workspace_material_service: RuntimeWorkspaceMaterialService,
        proposal_workflow_service: object | None = None,
        rp_block_read_service: object | None = None,
        worker_registry_service: object | None = None,
        worker_memory_service: object | None = None,
        core_state_as_of_resolver: object | None = None,
        llm_gateway: StoryLlmGateway | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._runtime_workspace_material_service = runtime_workspace_material_service
        self._llm_gateway = llm_gateway or StoryLlmGateway()
        # Keep these constructor seams for factory/test compatibility even though
        # Stage W W1-W4 intentionally does not enter proposal/worker mutation paths.
        self._proposal_workflow_service = proposal_workflow_service
        self._rp_block_read_service = rp_block_read_service
        self._worker_registry_service = worker_registry_service
        self._worker_memory_service = worker_memory_service
        self._core_state_as_of_resolver = core_state_as_of_resolver

    def start_session(self, request: BrainstormSessionStartRequest) -> BrainstormSession:
        self._ensure_identity_matches_session(request.identity)
        brainstorm_id = f"brainstorm_{uuid4().hex}"
        session = BrainstormSession(
            brainstorm_id=brainstorm_id,
            identity=request.identity,
            status=BrainstormSessionStatus.ACTIVE,
            created_by=request.actor,
            updated_by=request.actor,
            windows=[self._new_window(identity=request.identity, brainstorm_id=brainstorm_id)],
            metadata={
                "runtime_workspace_semantics": True,
                "temporary": True,
                "source_of_truth": False,
                "writer_discussion_mode": True,
                "batch_submit_stage": "w1_w4",
                **dict(request.metadata or {}),
            },
        )
        self._record_session_revision(session)
        return session

    def get_session(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        brainstorm_id: str,
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(identity)
        return self._load_latest_session(identity=identity, brainstorm_id=brainstorm_id)

    async def discuss_session(
        self,
        *,
        brainstorm_id: str,
        request: BrainstormDiscussionRequest,
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(request.identity)
        session = self._load_latest_session(
            identity=request.identity,
            brainstorm_id=brainstorm_id,
        )
        if session.status == BrainstormSessionStatus.CLOSED:
            raise StoryBrainstormServiceError("brainstorm_session_closed", brainstorm_id)
        active_window = self._ensure_active_window(session)
        user_message = BrainstormMessage(
            message_id=f"brainstorm-msg-{uuid4().hex}",
            role="user",
            content_text=request.prompt,
        )
        assistant_text, usage = await self._llm_gateway.complete_text_with_usage(
            model_id=request.model_id,
            provider_id=request.provider_id,
            messages=self._discussion_messages(session=session, prompt=request.prompt),
            temperature=0.4,
            max_tokens=1200,
        )
        assistant_message = BrainstormMessage(
            message_id=f"brainstorm-msg-{uuid4().hex}",
            role="assistant",
            content_text=assistant_text.strip() or "我还需要你补充一点具体信息。",
        )
        updated_window = active_window.model_copy(
            update={
                "messages": [
                    *active_window.messages,
                    user_message,
                    assistant_message,
                ],
                "source_message_refs": [
                    *active_window.source_message_refs,
                    user_message.message_id,
                    assistant_message.message_id,
                ],
                "updated_at": _utcnow(),
            }
        )
        updated = session.model_copy(
            update={
                "windows": _replace_window(session.windows, updated_window),
                "updated_by": request.actor,
                "updated_at": _utcnow(),
                "revision": session.revision + 1,
                "summary_trace": {
                    **dict(session.summary_trace or {}),
                    "last_discussion_usage": usage,
                    "last_discussion_window_id": updated_window.window_id,
                    "last_discussion_model_id": request.model_id,
                    "last_discussion_provider_id": request.provider_id,
                },
            }
        )
        self._record_session_revision(updated, previous=session)
        return updated

    async def summarize_session(
        self,
        *,
        brainstorm_id: str,
        request: BrainstormSummarizeRequest,
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(request.identity)
        session = self._load_latest_session(
            identity=request.identity,
            brainstorm_id=brainstorm_id,
        )
        if session.status == BrainstormSessionStatus.CLOSED:
            raise StoryBrainstormServiceError("brainstorm_session_closed", brainstorm_id)
        active_window = self._find_active_window(session)
        if active_window is None:
            raise StoryBrainstormServiceError(
                "brainstorm_summarize_no_active_window",
                brainstorm_id,
            )
        if not active_window.messages:
            raise StoryBrainstormServiceError(
                "brainstorm_summarize_window_empty",
                brainstorm_id,
            )
        structured = await self._run_structured_summary(
            session=session,
            window=active_window,
            request=request,
        )
        flushed_window = self._flush_window(
            active_window,
            reason=BrainstormContextFlushReason.SUMMARIZE,
        )
        now = _utcnow()
        batch_id = f"{brainstorm_id}:batch:{uuid4().hex}"
        items = [
            BrainstormBatchItem(
                item_id=f"{batch_id}:item:{uuid4().hex}",
                batch_id=batch_id,
                brainstorm_id=brainstorm_id,
                session_id=request.identity.session_id,
                branch_head_id=request.identity.branch_head_id,
                turn_id=request.identity.turn_id,
                runtime_profile_snapshot_id=request.identity.runtime_profile_snapshot_id,
                text=item_text,
                source_kind=BrainstormItemSourceKind.SUMMARIZED,
                status=BrainstormItemStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            for item_text in structured.items[: request.max_items]
        ]
        batch = BrainstormBatch(
            batch_id=batch_id,
            brainstorm_id=brainstorm_id,
            session_id=request.identity.session_id,
            branch_head_id=request.identity.branch_head_id,
            turn_id=request.identity.turn_id,
            runtime_profile_snapshot_id=request.identity.runtime_profile_snapshot_id,
            source_window_id=flushed_window.window_id,
            status=BrainstormBatchStatus.DRAFT,
            frozen=False,
            items=items,
            created_at=now,
            updated_at=now,
        )
        updated = session.model_copy(
            update={
                "windows": _replace_window(session.windows, flushed_window),
                "batches": [*session.batches, batch],
                "updated_by": request.actor,
                "updated_at": now,
                "revision": session.revision + 1,
                "summary_trace": {
                    **dict(session.summary_trace or {}),
                    "operation_kind": "brainstorm_summarize",
                    "schema_id": "rp.story.brainstorm_items.v2",
                    "item_count": len(items),
                    "model_id": request.model_id,
                    "provider_id": request.provider_id,
                    "source_window_id": flushed_window.window_id,
                    "fail_closed": True,
                },
            }
        )
        self._record_session_revision(updated, previous=session)
        return updated

    def continue_writing(
        self,
        *,
        brainstorm_id: str,
        request: BrainstormContinueWritingRequest,
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(request.identity)
        session = self._load_latest_session(
            identity=request.identity,
            brainstorm_id=brainstorm_id,
        )
        active_window = self._find_active_window(session)
        if active_window is None or not active_window.messages:
            return session
        flushed_window = self._flush_window(
            active_window,
            reason=BrainstormContextFlushReason.CONTINUE_WRITING,
        )
        updated = session.model_copy(
            update={
                "windows": _replace_window(session.windows, flushed_window),
                "updated_by": request.actor,
                "updated_at": _utcnow(),
                "revision": session.revision + 1,
            }
        )
        self._record_session_revision(updated, previous=session)
        return updated

    def create_item(
        self,
        *,
        brainstorm_id: str,
        batch_id: str,
        request: BrainstormItemCreateRequest,
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(request.identity)
        session = self._load_latest_session(
            identity=request.identity,
            brainstorm_id=brainstorm_id,
        )
        batch = self._require_batch(session, batch_id=batch_id)
        self._ensure_batch_editable(batch)
        now = _utcnow()
        new_item = BrainstormBatchItem(
            item_id=f"{batch_id}:item:{uuid4().hex}",
            batch_id=batch_id,
            brainstorm_id=brainstorm_id,
            session_id=request.identity.session_id,
            branch_head_id=request.identity.branch_head_id,
            turn_id=request.identity.turn_id,
            runtime_profile_snapshot_id=request.identity.runtime_profile_snapshot_id,
            text=request.text,
            source_kind=BrainstormItemSourceKind.USER_ADDED,
            status=BrainstormItemStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        updated_batch = batch.model_copy(
            update={
                "items": [*batch.items, new_item],
                "updated_at": now,
            }
        )
        updated = session.model_copy(
            update={
                "batches": _replace_batch(session.batches, updated_batch),
                "updated_by": request.actor,
                "updated_at": now,
                "revision": session.revision + 1,
            }
        )
        self._record_session_revision(updated, previous=session)
        return updated

    def update_item(
        self,
        *,
        brainstorm_id: str,
        batch_id: str,
        item_id: str,
        request: BrainstormItemUpdateRequest,
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(request.identity)
        session = self._load_latest_session(
            identity=request.identity,
            brainstorm_id=brainstorm_id,
        )
        batch = self._require_batch(session, batch_id=batch_id)
        self._ensure_batch_editable(batch)
        updated_items: list[BrainstormBatchItem] = []
        found = False
        now = _utcnow()
        for item in batch.items:
            if item.item_id != item_id:
                updated_items.append(item)
                continue
            found = True
            if item.status == BrainstormItemStatus.DELETED and request.text is not None:
                raise StoryBrainstormServiceError(
                    "brainstorm_deleted_item_read_only",
                    item_id,
                )
            item_updates: dict[str, Any] = {"updated_at": now}
            if request.status is not None:
                item_updates["status"] = BrainstormItemStatus(request.status)
            if request.text is not None:
                item_updates["text"] = request.text
            updated_items.append(item.model_copy(update=item_updates))
        if not found:
            raise StoryBrainstormServiceError("brainstorm_item_not_found", item_id)
        updated_batch = batch.model_copy(
            update={
                "items": updated_items,
                "updated_at": now,
            }
        )
        updated = session.model_copy(
            update={
                "batches": _replace_batch(session.batches, updated_batch),
                "updated_by": request.actor,
                "updated_at": now,
                "revision": session.revision + 1,
            }
        )
        self._record_session_revision(updated, previous=session)
        return updated

    def submit_batch(
        self,
        *,
        brainstorm_id: str,
        batch_id: str,
        request: BrainstormBatchSubmitRequest,
    ) -> tuple[BrainstormSession, BrainstormBatchSubmitReceipt]:
        self._ensure_identity_matches_session(request.identity)
        session = self._load_latest_session(
            identity=request.identity,
            brainstorm_id=brainstorm_id,
        )
        batch = self._require_batch(session, batch_id=batch_id)
        self._ensure_batch_editable(batch)
        active_items = [item for item in batch.items if item.status == BrainstormItemStatus.ACTIVE]
        if not active_items:
            raise StoryBrainstormServiceError(
                "brainstorm_batch_submit_empty",
                batch_id,
            )
        now = _utcnow()
        updated_items = [
            item.model_copy(
                update={
                    "status": (
                        BrainstormItemStatus.PENDING_PROCESSING
                        if item.status == BrainstormItemStatus.ACTIVE
                        else item.status
                    ),
                    "updated_at": now,
                }
            )
            for item in batch.items
        ]
        updated_batch = batch.model_copy(
            update={
                "status": BrainstormBatchStatus.PENDING_PROCESSING,
                "frozen": True,
                "items": updated_items,
                "updated_at": now,
                "submitted_at": now,
            }
        )
        updated_session = session.model_copy(
            update={
                "batches": _replace_batch(session.batches, updated_batch),
                "updated_by": request.actor,
                "updated_at": now,
                "revision": session.revision + 1,
            }
        )
        self._record_session_revision(updated_session, previous=session)
        receipt = BrainstormBatchSubmitReceipt(
            brainstorm_id=brainstorm_id,
            batch_id=batch_id,
            identity=request.identity,
            status="pending_processing",
            submitted_item_ids=[item.item_id for item in active_items],
            deleted_item_ids=[
                item.item_id
                for item in batch.items
                if item.status == BrainstormItemStatus.DELETED
            ],
        )
        return updated_session, receipt

    def close_session(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        brainstorm_id: str,
        actor: str,
        reason: str = "user_closed_noop",
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(identity)
        session = self._load_latest_session(identity=identity, brainstorm_id=brainstorm_id)
        updated = session.model_copy(
            update={
                "status": BrainstormSessionStatus.CLOSED,
                "close_reason": reason,
                "updated_by": actor,
                "updated_at": _utcnow(),
                "revision": session.revision + 1,
            }
        )
        self._record_session_revision(updated, previous=session)
        return updated

    async def _run_structured_summary(
        self,
        *,
        session: BrainstormSession,
        window: BrainstormContextWindow,
        request: BrainstormSummarizeRequest,
    ) -> BrainstormSummarizeOutput:
        if request.dry_run_items is not None:
            return BrainstormSummarizeOutput(items=list(request.dry_run_items))
        if request.model_id is None:
            raise StoryBrainstormServiceError(
                "brainstorm_summarize_model_required",
                session.brainstorm_id,
            )
        text, usage = await self._llm_gateway.complete_text_with_usage(
            model_id=request.model_id,
            provider_id=request.provider_id,
            messages=self._summary_messages(session=session, window=window),
            temperature=0,
            max_tokens=900,
        )
        try:
            payload = self._llm_gateway.extract_json_object(text)
            structured = BrainstormSummarizeOutput.model_validate(payload)
        except Exception as exc:
            raise StoryBrainstormServiceError(
                "brainstorm_summarize_invalid_output",
                str(exc),
            ) from exc
        session.summary_trace.update({"usage": usage})
        return structured

    def _discussion_messages(
        self,
        *,
        session: BrainstormSession,
        prompt: str,
    ) -> list[ChatMessage]:
        active_window = self._ensure_active_window(session)
        context = self._chapter_context(session.identity.session_id)
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are the writer brainstorm discussion persona for a story runtime. "
                    "Discuss chapter direction, character setup, foreshadowing, memory-change wishes, "
                    "and unresolved intent with the user. Ask clarifying questions when the request is underspecified. "
                    "Do not write story prose, do not output memory routing fields, and do not claim any Core/Recall/Archival mutation happened."
                ),
            ),
            ChatMessage(role="system", content=self._chapter_context_prompt(context)),
        ]
        for message in active_window.messages:
            messages.append(
                ChatMessage(role=message.role, content=message.content_text)
            )
        messages.append(ChatMessage(role="user", content=prompt))
        return messages

    def _summary_messages(
        self,
        *,
        session: BrainstormSession,
        window: BrainstormContextWindow,
    ) -> list[ChatMessage]:
        context = self._chapter_context(session.identity.session_id)
        transcript = self._window_transcript(window)
        return [
            ChatMessage(
                role="system",
                content=(
                    "You are running the dedicated brainstorm_summarize operation. "
                    "Return JSON only with the exact shape {\"items\":[\"...\"]}. "
                    "Each item must be one concise user-intent summary string. "
                    "Do not include uncertainty, suggested_question, evidence_refs, "
                    "routing fields, target_layer, target_domain, operation_kind, "
                    "field_path, old_value, or new_value."
                ),
            ),
            ChatMessage(role="system", content=self._chapter_context_prompt(context)),
            ChatMessage(
                role="user",
                content=(
                    "Summarize the current brainstorm context window into editable user intent items.\n\n"
                    f"{transcript}"
                ),
            ),
        ]

    def _chapter_context(self, session_id: str) -> _ChapterBrainstormContext:
        story_session = self._story_session_service.get_session(session_id)
        if story_session is None:
            return _ChapterBrainstormContext("", "", [], "")
        snapshot = self._story_session_service.build_chapter_snapshot(
            session_id=story_session.session_id,
            chapter_index=story_session.current_chapter_index,
        )
        outline_text = ""
        accepted_outline = snapshot.chapter.accepted_outline_json or {}
        if isinstance(accepted_outline, dict):
            outline_text = str(accepted_outline.get("content_text") or "").strip()
        accepted_segments = [
            str(artifact.content_text or "").strip()
            for artifact in snapshot.artifacts
            if artifact.artifact_kind.value == "story_segment"
            and artifact.status.value == "accepted"
            and str(artifact.content_text or "").strip()
        ]
        current_title = str(
            dict(story_session.current_state_json or {}).get("chapter_digest", {}).get(
                "title", ""
            )
        ).strip()
        phase = getattr(snapshot.chapter.phase, "value", snapshot.chapter.phase)
        return _ChapterBrainstormContext(
            phase=str(phase or "").strip(),
            outline_text=outline_text,
            accepted_segments=accepted_segments[-2:],
            current_title=current_title,
        )

    def _chapter_context_prompt(self, context: _ChapterBrainstormContext) -> str:
        lines = ["Current branch-visible story context:"]
        if context.phase:
            lines.append(f"- phase: {context.phase}")
        if context.current_title:
            lines.append(f"- chapter_title: {context.current_title}")
        if context.outline_text:
            lines.append(f"- accepted_outline: {context.outline_text}")
        if context.accepted_segments:
            lines.append("- accepted_segments:")
            for segment in context.accepted_segments:
                lines.append(f"  - {segment}")
        return "\n".join(lines)

    def _window_transcript(self, window: BrainstormContextWindow) -> str:
        lines: list[str] = []
        for message in window.messages:
            lines.append(f"{message.role}: {message.content_text}")
        return "\n".join(lines)

    def _find_active_window(
        self,
        session: BrainstormSession,
    ) -> BrainstormContextWindow | None:
        for window in reversed(session.windows):
            if window.status == BrainstormContextWindowStatus.ACTIVE:
                return window
        return None

    def _ensure_active_window(self, session: BrainstormSession) -> BrainstormContextWindow:
        existing = self._find_active_window(session)
        if existing is not None:
            return existing
        return self._new_window(
            identity=session.identity,
            brainstorm_id=session.brainstorm_id,
        )

    def _new_window(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        brainstorm_id: str,
    ) -> BrainstormContextWindow:
        now = _utcnow()
        return BrainstormContextWindow(
            window_id=f"{brainstorm_id}:window:{uuid4().hex}",
            brainstorm_id=brainstorm_id,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            turn_id=identity.turn_id,
            runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
            status=BrainstormContextWindowStatus.ACTIVE,
            messages=[],
            source_message_refs=[],
            created_at=now,
            updated_at=now,
        )

    def _flush_window(
        self,
        window: BrainstormContextWindow,
        *,
        reason: BrainstormContextFlushReason,
    ) -> BrainstormContextWindow:
        return window.model_copy(
            update={
                "status": BrainstormContextWindowStatus.FLUSHED,
                "flush_reason": reason,
                "flushed_at": _utcnow(),
                "updated_at": _utcnow(),
            }
        )

    def _require_batch(self, session: BrainstormSession, *, batch_id: str) -> BrainstormBatch:
        for batch in session.batches:
            if batch.batch_id == batch_id:
                return batch
        raise StoryBrainstormServiceError("brainstorm_batch_not_found", batch_id)

    def _ensure_batch_editable(self, batch: BrainstormBatch) -> None:
        if batch.status != BrainstormBatchStatus.DRAFT or batch.frozen:
            raise StoryBrainstormServiceError("brainstorm_batch_frozen", batch.batch_id)

    def _load_latest_session(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        brainstorm_id: str,
    ) -> BrainstormSession:
        matches: list[BrainstormSession] = []
        for material in self._runtime_workspace_material_service.list_materials(
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.BRAINSTORM_SESSION,
            domain=BRAINSTORM_MATERIAL_DOMAIN,
        ):
            payload = dict(material.payload or {})
            if payload.get("brainstorm_id") != brainstorm_id:
                continue
            matches.append(BrainstormSession.model_validate(payload))
        if not matches:
            raise StoryBrainstormServiceError("brainstorm_session_not_found", brainstorm_id)
        return max(matches, key=lambda item: item.revision)

    def _record_session_revision(
        self,
        session: BrainstormSession,
        *,
        previous: BrainstormSession | None = None,
    ) -> None:
        if previous is not None:
            try:
                self._runtime_workspace_material_service.update_lifecycle(
                    identity=previous.identity,
                    material_id=self._material_id(previous),
                    lifecycle=RuntimeWorkspaceMaterialLifecycle.INVALIDATED,
                    reason="brainstorm_session_revision_superseded",
                )
            except RuntimeWorkspaceMaterialServiceError:
                pass
        self._runtime_workspace_material_service.record_material(
            RuntimeWorkspaceMaterial(
                material_id=self._material_id(session),
                material_kind=RuntimeWorkspaceMaterialKind.BRAINSTORM_SESSION,
                identity=session.identity,
                domain=BRAINSTORM_MATERIAL_DOMAIN,
                domain_path=BRAINSTORM_MATERIAL_DOMAIN_PATH,
                payload=session.model_dump(mode="json"),
                visibility=RuntimeWorkspaceMaterialVisibility.REVIEW_VISIBLE.value,
                created_by="writer.brainstorm",
                metadata={
                    "payload_kind": "brainstorm_session",
                    "brainstorm_id": session.brainstorm_id,
                    "revision": session.revision,
                    "temporary": True,
                    "source_of_truth": False,
                },
            )
        )

    @staticmethod
    def _material_id(session: BrainstormSession) -> str:
        return f"{session.brainstorm_id}:state:{session.revision}"

    def _ensure_identity_matches_session(self, identity: MemoryRuntimeIdentity) -> None:
        story_session = self._story_session_service.get_session(identity.session_id)
        if story_session is None:
            raise StoryBrainstormServiceError("story_session_not_found", identity.session_id)
        if story_session.story_id != identity.story_id:
            raise StoryBrainstormServiceError(
                "brainstorm_identity_story_mismatch",
                identity.story_id,
            )


def _replace_window(
    windows: list[BrainstormContextWindow],
    updated_window: BrainstormContextWindow,
) -> list[BrainstormContextWindow]:
    replaced = False
    result: list[BrainstormContextWindow] = []
    for window in windows:
        if window.window_id == updated_window.window_id:
            result.append(updated_window)
            replaced = True
        else:
            result.append(window)
    if not replaced:
        result.append(updated_window)
    return result


def _replace_batch(
    batches: list[BrainstormBatch],
    updated_batch: BrainstormBatch,
) -> list[BrainstormBatch]:
    result: list[BrainstormBatch] = []
    replaced = False
    for batch in batches:
        if batch.batch_id == updated_batch.batch_id:
            result.append(updated_batch)
            replaced = True
        else:
            result.append(batch)
    if not replaced:
        result.append(updated_batch)
    return result
