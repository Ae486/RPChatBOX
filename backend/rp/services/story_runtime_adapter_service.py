"""Thin compatibility adapters for legacy longform runtime surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rp.models.story_runtime import (
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
)
from rp.models.worker_runtime_contracts import (
    RuntimeWorkerRegistration,
    WorkerExecutionRequest,
    WorkerResult,
    WorkerResultStatus,
)

LONGFORM_ADAPTER_POLICY_ID = "story_runtime.longform_compat_adapter.v1"

WritingOperationMode = Literal["writing", "rewrite", "discussion"]


@dataclass(frozen=True)
class LegacyLongformCommandTranslation:
    """Adapter output for old product commands; not a runtime truth model."""

    command_kind: LongformTurnCommandKind
    operation_mode: WritingOperationMode
    output_kind: StoryArtifactKind
    deterministic_action: str | None
    notes: tuple[str, ...]
    adapter_policy_id: str = LONGFORM_ADAPTER_POLICY_ID
    command_surface: str = "legacy_longform_command"

    def metadata(self) -> dict[str, object]:
        return {
            "adapter_policy_id": self.adapter_policy_id,
            "command_surface": self.command_surface,
            "legacy_command": self.command_kind.value,
            "operation_mode": self.operation_mode,
            "output_kind": self.output_kind.value,
            "deterministic_action": self.deterministic_action,
            "notes": list(self.notes),
        }


class StoryRuntimeAdapterService:
    """Map legacy longform shapes into already-frozen runtime contracts.

    This service intentionally does not decide which worker runs, what memory is true,
    or which context slots enter a writer packet. It only translates old command and
    result shapes at the boundary where new runtime contracts still accept them.
    """

    def coerce_legacy_command_kind(self, command_kind: str) -> LongformTurnCommandKind:
        try:
            return LongformTurnCommandKind(command_kind)
        except ValueError:
            return LongformTurnCommandKind.WRITE_NEXT_SEGMENT

    def translate_legacy_command(
        self,
        *,
        command_kind: LongformTurnCommandKind | None,
        plan: OrchestratorPlan | None = None,
    ) -> LegacyLongformCommandTranslation:
        resolved_command = command_kind or LongformTurnCommandKind.WRITE_NEXT_SEGMENT
        operation_mode: WritingOperationMode = "writing"
        if resolved_command == LongformTurnCommandKind.DISCUSS_OUTLINE:
            operation_mode = "discussion"
        elif resolved_command == LongformTurnCommandKind.REWRITE_PENDING_SEGMENT:
            operation_mode = "rewrite"
        elif plan is not None and plan.output_kind == StoryArtifactKind.DISCUSSION_MESSAGE:
            operation_mode = "discussion"

        deterministic_action = self._deterministic_action(resolved_command)
        output_kind = plan.output_kind if plan is not None else self._default_output_kind(
            resolved_command=resolved_command,
            operation_mode=operation_mode,
        )
        notes = [
            "adapter_boundary:legacy_command_translation",
            "runtime_contract_owner:writing_worker_contract",
            f"legacy_command:{resolved_command.value}",
        ]
        if deterministic_action is not None:
            notes.append(f"deterministic_action:{deterministic_action}")
        return LegacyLongformCommandTranslation(
            command_kind=resolved_command,
            operation_mode=operation_mode,
            output_kind=output_kind,
            deterministic_action=deterministic_action,
            notes=tuple(notes),
        )

    def build_legacy_post_write_plan(
        self,
        *,
        command_kind: LongformTurnCommandKind,
    ) -> OrchestratorPlan:
        translation = self.translate_legacy_command(
            command_kind=command_kind,
            plan=None,
        )
        notes = [
            "adapter_input:legacy_orchestrator_plan",
            "not_canonical_worker_plan",
            f"adapter_policy:{LONGFORM_ADAPTER_POLICY_ID}",
            f"legacy_command:{translation.command_kind.value}",
        ]
        if translation.deterministic_action is not None:
            notes.append(f"deterministic_action:{translation.deterministic_action}")
        return OrchestratorPlan(
            output_kind=translation.output_kind,
            writer_instruction="Post-write maintenance adapter input.",
            notes=notes,
        )

    def adapt_specialist_bundle_to_worker_result(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        bundle: SpecialistResultBundle,
    ) -> WorkerResult:
        return WorkerResult(
            worker_id=request.worker_id,
            phase=request.phase,
            result_status=WorkerResultStatus.COMPLETED,
            writer_hints=[{"text": hint} for hint in bundle.writer_hints],
            proposal_candidates=(
                [
                    {
                        "candidate_kind": "legacy_state_patch",
                        "payload": bundle.state_patch_proposals,
                    }
                ]
                if bundle.state_patch_proposals
                else []
            ),
            recall_candidates=(
                [
                    {
                        "candidate_kind": "legacy_recall_summary",
                        "text": bundle.recall_summary_text,
                    }
                ]
                if bundle.recall_summary_text
                else []
            ),
            validation_findings=[
                {"message": finding} for finding in bundle.validation_findings
            ],
            trace_summary={
                "adapter": "LongformSpecialistService",
                "adapter_policy_id": LONGFORM_ADAPTER_POLICY_ID,
                "adapter_role": "legacy_executor_bridge",
                "canonical_contract_owner": "WorkerExecutionPlan",
                "legacy_plan_role": "adapter_input",
                "policy_id": registration.execution_policy.policy_id,
                "context_packet_ref": request.context_packet_ref,
            },
            metadata={
                "legacy_bundle_kind": "SpecialistResultBundle",
                "adapter_boundary": "legacy_bundle_to_worker_result",
                "runtime_truth": "worker_runtime_contract",
                "source_worker_id": registration.source_worker_id,
                "context_packet_ref": request.context_packet_ref,
                "foundation_digest": list(bundle.foundation_digest),
                "blueprint_digest": list(bundle.blueprint_digest),
                "current_outline_digest": list(bundle.current_outline_digest),
                "recent_segment_digest": list(bundle.recent_segment_digest),
                "current_state_digest": list(bundle.current_state_digest),
                "summary_updates": list(bundle.summary_updates),
            },
        )

    @staticmethod
    def _deterministic_action(
        command_kind: LongformTurnCommandKind,
    ) -> str | None:
        if command_kind == LongformTurnCommandKind.ACCEPT_OUTLINE:
            return "accept_outline"
        if command_kind == LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT:
            return "accept_pending_segment"
        if command_kind == LongformTurnCommandKind.COMPLETE_CHAPTER:
            return "complete_chapter"
        return None

    @staticmethod
    def _default_output_kind(
        *,
        resolved_command: LongformTurnCommandKind,
        operation_mode: WritingOperationMode,
    ) -> StoryArtifactKind:
        if resolved_command == LongformTurnCommandKind.GENERATE_OUTLINE:
            return StoryArtifactKind.CHAPTER_OUTLINE
        if operation_mode == "discussion":
            return StoryArtifactKind.DISCUSSION_MESSAGE
        return StoryArtifactKind.STORY_SEGMENT
