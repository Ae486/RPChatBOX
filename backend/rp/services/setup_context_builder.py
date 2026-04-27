"""Setup context packet assembly for the SetupAgent MVP."""

from __future__ import annotations

from typing import Any, Literal

from rp.models.setup_handoff import (
    SetupContextBuilderInput,
    SetupContextPacket,
    SetupStageChunkDescription,
    SetupStageHandoffPacket,
)
from rp.models.setup_workspace import SetupStepId
from rp.services.setup_workspace_service import SetupWorkspaceService


class SetupContextBuilder:
    """Build a stable setup context packet from SetupWorkspace state."""

    _COMPACT_CONTEXT_TOKEN_BUDGET = 1200
    _STEP_ORDER = SetupWorkspaceService._STEP_ORDER

    def __init__(self, workspace_service: SetupWorkspaceService):
        self._workspace_service = workspace_service

    def build(self, input_model: SetupContextBuilderInput) -> SetupContextPacket:
        workspace = self._workspace_service.get_workspace(input_model.workspace_id)
        if workspace is None:
            raise ValueError(f"SetupWorkspace not found: {input_model.workspace_id}")

        current_step = SetupStepId(input_model.current_step)
        context_profile = self._context_profile(input_model.token_budget)
        prior_stage_handoffs = self._collect_prior_stage_handoffs(
            workspace=workspace,
            current_step=current_step,
            context_profile=context_profile,
        )
        current_draft_snapshot = self._current_draft_snapshot(workspace, current_step)
        step_asset_preview = [
            {
                "asset_id": asset.asset_id,
                "asset_kind": asset.asset_kind,
                "title": asset.title,
                "parse_status": asset.parse_status.value,
                "mapped_targets": list(asset.mapped_targets),
            }
            for asset in workspace.imported_assets
            if asset.step_id == current_step
        ]
        delta_ids = set(input_model.user_edit_delta_ids)
        user_edit_deltas = [
            {
                "delta_id": delta.delta_id,
                "target_block": delta.target_block,
                "target_ref": delta.target_ref,
                "changes": [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in delta.changes
                ],
            }
            for delta in workspace.pending_user_edit_deltas
            if (
                not delta_ids
                and delta.step_id == current_step
                and delta.consumed_at is None
            )
            or delta.delta_id in delta_ids
        ]
        committed_summaries = [handoff.summary for handoff in prior_stage_handoffs]
        spotlights = [
            spotlight
            for handoff in prior_stage_handoffs
            for spotlight in handoff.spotlights
        ]

        return SetupContextPacket(
            workspace_id=workspace.workspace_id,
            current_step=current_step.value,
            context_profile=context_profile,
            committed_summaries=committed_summaries,
            current_draft_snapshot=current_draft_snapshot,
            step_asset_preview=step_asset_preview,
            user_prompt=input_model.user_prompt,
            user_edit_deltas=user_edit_deltas,
            spotlights=spotlights[:10],
            prior_stage_handoffs=prior_stage_handoffs,
        )

    @staticmethod
    def _context_profile(
        token_budget: int | None,
    ) -> Literal["standard", "compact"]:
        if (
            token_budget is not None
            and token_budget < SetupContextBuilder._COMPACT_CONTEXT_TOKEN_BUDGET
        ):
            return "compact"
        return "standard"

    @classmethod
    def _collect_prior_stage_handoffs(
        cls,
        *,
        workspace,
        current_step: SetupStepId,
        context_profile: str,
    ) -> list[SetupStageHandoffPacket]:
        try:
            current_index = cls._STEP_ORDER.index(current_step)
        except ValueError:
            return []
        if current_index <= 0:
            return []

        latest_commit_by_step = cls._latest_commit_by_step(workspace)
        handoffs: list[SetupStageHandoffPacket] = []
        for step_id in cls._STEP_ORDER[:current_index]:
            commit = latest_commit_by_step.get(step_id)
            if commit is None:
                continue
            handoffs.append(
                cls._build_stage_handoff(
                    commit=commit,
                    context_profile=context_profile,
                )
            )
        return handoffs

    @classmethod
    def _latest_commit_by_step(cls, workspace) -> dict[SetupStepId, Any]:
        latest: dict[SetupStepId, Any] = {}
        ordered_commits = sorted(
            workspace.accepted_commits,
            key=lambda item: (item.created_at, cls._STEP_ORDER.index(item.step_id)),
        )
        for commit in ordered_commits:
            latest[commit.step_id] = commit
        return latest

    @classmethod
    def _build_stage_handoff(
        cls,
        *,
        commit,
        context_profile: str,
    ) -> SetupStageHandoffPacket:
        compact = context_profile == "compact"
        return SetupStageHandoffPacket(
            step_id=commit.step_id,
            commit_id=commit.commit_id,
            summary=cls._commit_summary(commit=commit, compact=compact),
            committed_refs=list(commit.committed_refs),
            spotlights=list(commit.spotlights[:5]),
            chunk_descriptions=(
                []
                if compact
                else cls._build_chunk_descriptions(
                    commit=commit,
                    compact=False,
                )
            ),
            created_at=commit.created_at,
        )

    @staticmethod
    def _commit_summary(*, commit, compact: bool) -> str:
        summary = (
            commit.summary_tier_0
            if compact
            else commit.summary_tier_1 or commit.summary_tier_2
        )
        summary = (
            summary or commit.summary_tier_0 or f"Committed {commit.step_id.value}"
        )
        return summary if isinstance(summary, str) else str(summary)

    @classmethod
    def _build_chunk_descriptions(
        cls,
        *,
        commit,
        compact: bool,
    ) -> list[SetupStageChunkDescription]:
        chunks: list[SetupStageChunkDescription] = []
        for snapshot in commit.snapshots:
            if snapshot.block_type == "foundation":
                chunks.extend(cls._foundation_chunk_descriptions(snapshot.payload))
                continue
            if snapshot.block_type == "longform_blueprint":
                chunks.extend(cls._blueprint_chunk_descriptions(snapshot.payload))
                continue
            description = cls._generic_snapshot_description(
                block_type=snapshot.block_type,
                payload=snapshot.payload,
            )
            if description is None:
                continue
            chunks.append(
                SetupStageChunkDescription(
                    chunk_ref=f"{snapshot.block_type}:{commit.commit_id}",
                    block_type=snapshot.block_type,
                    title=snapshot.block_type,
                    description=description,
                )
            )
        return chunks[: (4 if compact else 8)]

    @classmethod
    def _foundation_chunk_descriptions(
        cls,
        payload: dict[str, Any],
    ) -> list[SetupStageChunkDescription]:
        descriptions: list[SetupStageChunkDescription] = []
        for entry in payload.get("entries", [])[:6]:
            entry_id = str(entry.get("entry_id") or entry.get("path") or "foundation")
            domain = str(entry.get("domain") or "foundation")
            path = str(entry.get("path") or entry_id)
            title = str(entry.get("title") or path)
            description = f"{domain} | {path}"
            summary = cls._content_summary(entry.get("content"))
            if summary:
                description = f"{description} - {summary}"
            descriptions.append(
                SetupStageChunkDescription(
                    chunk_ref=f"foundation:{entry_id}",
                    block_type="foundation_entry",
                    title=title,
                    description=description,
                    metadata={
                        "domain": domain,
                        "path": path,
                        "entry_id": entry.get("entry_id"),
                    },
                )
            )
        return descriptions

    @classmethod
    def _blueprint_chunk_descriptions(
        cls,
        payload: dict[str, Any],
    ) -> list[SetupStageChunkDescription]:
        descriptions: list[SetupStageChunkDescription] = []
        overview = cls._join_parts(
            [
                cls._coerce_preview_text(payload.get("premise")),
                cls._coerce_preview_text(payload.get("central_conflict")),
                cls._coerce_preview_text(payload.get("chapter_strategy")),
            ]
        )
        if overview:
            descriptions.append(
                SetupStageChunkDescription(
                    chunk_ref="longform_blueprint:overview",
                    block_type="longform_blueprint",
                    title="Blueprint Overview",
                    description=overview,
                    metadata={"kind": "overview"},
                )
            )
        for chapter in payload.get("chapter_blueprints", [])[:6]:
            chapter_id = str(chapter.get("chapter_id") or "chapter")
            title = str(chapter.get("title") or chapter_id)
            description = cls._join_parts(
                [
                    cls._coerce_preview_text(chapter.get("purpose")),
                    cls._coerce_preview_text(
                        ", ".join(chapter.get("major_beats", [])[:2])
                    ),
                ]
            )
            if not description:
                description = "Chapter scaffold accepted for later drafting."
            descriptions.append(
                SetupStageChunkDescription(
                    chunk_ref=f"longform_blueprint:{chapter_id}",
                    block_type="chapter_blueprint",
                    title=title,
                    description=description,
                    metadata={
                        "chapter_id": chapter_id,
                        "purpose": chapter.get("purpose"),
                    },
                )
            )
        return descriptions

    @classmethod
    def _generic_snapshot_description(
        cls,
        *,
        block_type: str,
        payload: dict[str, Any],
    ) -> str | None:
        if block_type == "writing_contract":
            return (
                cls._join_parts(
                    [
                        cls._prefixed_preview("POV", payload.get("pov_rules")),
                        cls._prefixed_preview("Style", payload.get("style_rules")),
                        cls._prefixed_preview(
                            "Constraints",
                            payload.get("writing_constraints"),
                        ),
                    ]
                )
                or None
            )
        if block_type == "story_config":
            return (
                cls._join_parts(
                    [
                        cls._prefixed_preview(
                            "Model",
                            payload.get("model_profile_ref"),
                        ),
                        cls._prefixed_preview(
                            "Worker",
                            payload.get("worker_profile_ref"),
                        ),
                        cls._coerce_preview_text(payload.get("notes")),
                    ]
                )
                or None
            )
        return None

    @staticmethod
    def _content_summary(content: Any) -> str | None:
        if isinstance(content, dict):
            for key in ("summary", "description", "premise"):
                value = content.get(key)
                if value:
                    return str(value)
            for value in content.values():
                if isinstance(value, str) and value:
                    return value
        if isinstance(content, str) and content:
            return content
        return None

    @staticmethod
    def _prefixed_preview(label: str, value: Any) -> str | None:
        preview = SetupContextBuilder._coerce_preview_text(value)
        if not preview:
            return None
        return f"{label}: {preview}"

    @staticmethod
    def _coerce_preview_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            preview = value.strip()
            return preview or None
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            if not items:
                return None
            return ", ".join(items[:3])
        return str(value).strip() or None

    @staticmethod
    def _join_parts(parts: list[str | None]) -> str:
        return " | ".join(part for part in parts if part)

    @staticmethod
    def _current_draft_snapshot(workspace, current_step: SetupStepId) -> dict:
        if (
            current_step == SetupStepId.STORY_CONFIG
            and workspace.story_config_draft is not None
        ):
            return workspace.story_config_draft.model_dump(
                mode="json",
                exclude_none=True,
            )
        if (
            current_step == SetupStepId.WRITING_CONTRACT
            and workspace.writing_contract_draft is not None
        ):
            return workspace.writing_contract_draft.model_dump(
                mode="json",
                exclude_none=True,
            )
        if (
            current_step == SetupStepId.FOUNDATION
            and workspace.foundation_draft is not None
        ):
            return workspace.foundation_draft.model_dump(
                mode="json",
                exclude_none=True,
            )
        if (
            current_step == SetupStepId.LONGFORM_BLUEPRINT
            and workspace.longform_blueprint_draft is not None
        ):
            return workspace.longform_blueprint_draft.model_dump(
                mode="json",
                exclude_none=True,
            )
        return {}
