"""Canonical metadata builders for RP memory materialization intake."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef


RECALL_LAYER = "recall"
ARCHIVAL_LAYER = "archival"
LONGFORM_STORY_RUNTIME_SOURCE_FAMILY = "longform_story_runtime"
SETUP_SOURCE_FAMILY = "setup_source"
HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT = "heavy_regression.chapter_close"
SCENE_CLOSE_EVENT = "scene_close"
SETUP_COMMIT_IMPORT_EVENT = "setup.commit_ingest"

CHAPTER_SUMMARY_KIND = "chapter_summary"
ACCEPTED_STORY_SEGMENT_KIND = "accepted_story_segment"
CONTINUITY_NOTE_KIND = "continuity_note"
SCENE_TRANSCRIPT_KIND = "scene_transcript"
CHARACTER_LONG_HISTORY_SUMMARY_KIND = "character_long_history_summary"
RETIRED_FORESHADOW_SUMMARY_KIND = "retired_foreshadow_summary"
FOUNDATION_ENTRY_SOURCE_TYPE = "foundation_entry"
LONGFORM_BLUEPRINT_SOURCE_TYPE = "longform_blueprint"
IMPORTED_ASSET_SOURCE_TYPE = "imported_asset"
RECALL_LIFECYCLE_ACTIVE = "active"
RECALL_LIFECYCLE_SUPERSEDED = "superseded"
RECALL_LIFECYCLE_INVALIDATED = "invalidated"
RECALL_LIFECYCLE_HIDDEN_BY_ROLLBACK = "hidden_by_rollback"
RECALL_LIFECYCLE_RECOMPUTED = "recomputed"
RECALL_VISIBILITY_STORY_GLOBAL = "story_global"
RECALL_VISIBILITY_BRANCH_SCOPED = "branch_scoped"
RECALL_VISIBILITY_SELECTED_BRANCHES = "selected_branches"
ARCHIVAL_LIFECYCLE_ACTIVE = "active"
ARCHIVAL_VISIBILITY_STORY_GLOBAL = "story_global"


class RecallLifecycleMetadata(BaseModel):
    """Canonical lifecycle payload attached to Recall source assets and chunks."""

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity | None = None
    materialization_kind: str
    lifecycle_state: str = RECALL_LIFECYCLE_ACTIVE
    visibility_scope: str | None = None
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    supersedes_refs: list[str] = Field(default_factory=list)
    invalidated_by_event_ids: list[str] = Field(default_factory=list)
    hidden_after_turn_id: str | None = None
    scene_ref: str | None = None

    @field_validator("materialization_kind", "lifecycle_state")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("visibility_scope")
    @classmethod
    def _normalize_visibility_scope(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _require_non_blank(value, field_name="visibility_scope")
        if normalized not in {
            RECALL_VISIBILITY_STORY_GLOBAL,
            RECALL_VISIBILITY_BRANCH_SCOPED,
            RECALL_VISIBILITY_SELECTED_BRANCHES,
        }:
            raise ValueError(f"unsupported visibility_scope: {normalized}")
        return normalized

    @field_validator("scene_ref", "hidden_after_turn_id")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("supersedes_refs", "invalidated_by_event_ids")
    @classmethod
    def _normalize_text_list(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _normalize_text_list(values, field_name=info.field_name or "value")

    @property
    def effective_visibility_scope(self) -> str:
        if self.visibility_scope is not None:
            return self.visibility_scope
        if self.identity is not None:
            return RECALL_VISIBILITY_BRANCH_SCOPED
        return RECALL_VISIBILITY_STORY_GLOBAL


def build_recall_materialization_metadata(
    *,
    materialization_kind: str,
    materialization_event: str,
    session_id: str,
    chapter_index: int,
    domain_path: str,
    identity: MemoryRuntimeIdentity | Mapping[str, Any] | None = None,
    lifecycle_state: str = RECALL_LIFECYCLE_ACTIVE,
    visibility_scope: str | None = None,
    source_refs: Sequence[MemorySourceRef | Mapping[str, Any]] | None = None,
    supersedes_refs: Sequence[str] | None = None,
    invalidated_by_event_ids: Sequence[str] | None = None,
    hidden_after_turn_id: str | None = None,
    scene_ref: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical Recall metadata and prevent caller-owned override drift."""

    normalized_kind = _require_non_blank(
        materialization_kind,
        field_name="materialization_kind",
    )
    normalized_event = _require_non_blank(
        materialization_event,
        field_name="materialization_event",
    )
    normalized_session_id = _require_non_blank(session_id, field_name="session_id")
    normalized_domain_path = _require_non_blank(
        domain_path,
        field_name="domain_path",
    )
    if chapter_index <= 0:
        raise ValueError("chapter_index must be positive")

    lifecycle = RecallLifecycleMetadata(
        identity=_normalize_runtime_identity(identity),
        materialization_kind=normalized_kind,
        lifecycle_state=lifecycle_state,
        visibility_scope=visibility_scope,
        source_refs=_normalize_source_refs(source_refs),
        supersedes_refs=list(supersedes_refs or []),
        invalidated_by_event_ids=list(invalidated_by_event_ids or []),
        hidden_after_turn_id=hidden_after_turn_id,
        scene_ref=scene_ref,
    )
    metadata = dict(extra or {})
    metadata.update(
        {
            "layer": RECALL_LAYER,
            "source_family": LONGFORM_STORY_RUNTIME_SOURCE_FAMILY,
            "materialization_event": normalized_event,
            "materialization_kind": normalized_kind,
            "materialized_to_recall": True,
            "source_type": normalized_kind,
            "session_id": normalized_session_id,
            "chapter_index": chapter_index,
            "domain": "chapter",
            "domain_path": normalized_domain_path,
            "runtime_identity": (
                lifecycle.identity.model_dump(mode="json")
                if lifecycle.identity is not None
                else None
            ),
            "branch_head_id": (
                lifecycle.identity.branch_head_id
                if lifecycle.identity is not None
                else None
            ),
            "owning_branch_head_id": (
                lifecycle.identity.branch_head_id
                if lifecycle.identity is not None
                else None
            ),
            "turn_id": (
                lifecycle.identity.turn_id if lifecycle.identity is not None else None
            ),
            "origin_turn_id": (
                lifecycle.identity.turn_id if lifecycle.identity is not None else None
            ),
            "runtime_profile_snapshot_id": (
                lifecycle.identity.runtime_profile_snapshot_id
                if lifecycle.identity is not None
                else None
            ),
            "lifecycle_state": lifecycle.lifecycle_state,
            "visibility_scope": lifecycle.effective_visibility_scope,
            "visibility_state": _visibility_state_for_lifecycle(
                lifecycle.lifecycle_state
            ),
            "source_refs": [
                item.model_dump(mode="json") for item in lifecycle.source_refs
            ],
            "supersedes_refs": list(lifecycle.supersedes_refs),
            "invalidated_by_event_ids": list(lifecycle.invalidated_by_event_ids),
            "hidden_after_turn_id": lifecycle.hidden_after_turn_id,
            "scene_ref": lifecycle.scene_ref,
        }
    )
    return metadata


def build_recall_seed_section(
    *,
    section_id: str,
    title: str,
    path: str,
    text: str,
    metadata: Mapping[str, Any],
    tags: Sequence[str],
) -> dict[str, Any]:
    """Build one retrieval-core seed section with canonical Recall metadata."""

    normalized_tags = _normalize_tags(tags)
    return {
        "section_id": _require_non_blank(section_id, field_name="section_id"),
        "title": _require_non_blank(title, field_name="title"),
        "path": _require_non_blank(path, field_name="path"),
        "level": 1,
        "text": text,
        "metadata": {
            **dict(metadata),
            "tags": normalized_tags,
        },
    }


def build_archival_source_metadata(
    *,
    source_type: str,
    import_event: str,
    workspace_id: str,
    commit_id: str,
    step_id: str,
    source_ref: str,
    domain: str,
    domain_path: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical Archival metadata and keep ownership fields memory-owned."""

    normalized_source_type = _require_non_blank(source_type, field_name="source_type")
    normalized_import_event = _require_non_blank(
        import_event,
        field_name="import_event",
    )
    normalized_workspace_id = _require_non_blank(
        workspace_id,
        field_name="workspace_id",
    )
    normalized_commit_id = _require_non_blank(commit_id, field_name="commit_id")
    normalized_step_id = _require_non_blank(step_id, field_name="step_id")
    normalized_source_ref = _require_non_blank(source_ref, field_name="source_ref")
    normalized_domain = _require_non_blank(domain, field_name="domain")
    normalized_domain_path = _require_non_blank(
        domain_path,
        field_name="domain_path",
    )

    metadata = dict(extra or {})
    metadata.update(
        {
            "layer": ARCHIVAL_LAYER,
            "source_family": SETUP_SOURCE_FAMILY,
            "import_event": normalized_import_event,
            "source_type": normalized_source_type,
            "source_origin": "setup_workspace",
            "materialized_to_archival": True,
            "materialized_to_recall": False,
            "authoritative_mutation": False,
            "workspace_id": normalized_workspace_id,
            "commit_id": normalized_commit_id,
            "step_id": normalized_step_id,
            "source_ref": normalized_source_ref,
            "domain": normalized_domain,
            "domain_path": normalized_domain_path,
            "source_version": 1,
            "source_asset_version": 1,
            "lifecycle_state": ARCHIVAL_LIFECYCLE_ACTIVE,
            "visibility_scope": ARCHIVAL_VISIBILITY_STORY_GLOBAL,
            "visibility_state": "active",
        }
    )
    return metadata


def build_archival_seed_section(
    *,
    section_id: str,
    title: str,
    path: str,
    text: str,
    metadata: Mapping[str, Any],
    tags: Sequence[str],
    level: int = 1,
) -> dict[str, Any]:
    """Build one retrieval-core seed section with canonical Archival metadata."""

    normalized_tags = _normalize_tags(tags)
    return {
        "section_id": _require_non_blank(section_id, field_name="section_id"),
        "title": _require_non_blank(title, field_name="title"),
        "path": _require_non_blank(path, field_name="path"),
        "level": max(1, int(level)),
        "text": text,
        "metadata": {
            **dict(metadata),
            "tags": normalized_tags,
        },
    }


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _normalize_runtime_identity(
    identity: MemoryRuntimeIdentity | Mapping[str, Any] | None,
) -> MemoryRuntimeIdentity | None:
    if identity is None:
        return None
    if isinstance(identity, MemoryRuntimeIdentity):
        return identity
    return MemoryRuntimeIdentity.model_validate(dict(identity))


def _normalize_source_refs(
    source_refs: Sequence[MemorySourceRef | Mapping[str, Any]] | None,
) -> list[MemorySourceRef]:
    normalized_refs: list[MemorySourceRef] = []
    seen: set[tuple[str, str]] = set()
    for item in source_refs or []:
        ref = (
            item
            if isinstance(item, MemorySourceRef)
            else MemorySourceRef.model_validate(dict(item))
        )
        key = (ref.source_type.casefold(), ref.source_id.casefold())
        if key in seen:
            continue
        seen.add(key)
        normalized_refs.append(ref)
    return normalized_refs


def _visibility_state_for_lifecycle(lifecycle_state: str) -> str:
    normalized = lifecycle_state.strip()
    if normalized in {
        RECALL_LIFECYCLE_SUPERSEDED,
        RECALL_LIFECYCLE_INVALIDATED,
        RECALL_LIFECYCLE_HIDDEN_BY_ROLLBACK,
    }:
        return normalized
    return "active"


def _normalize_text_list(values: Sequence[str], *, field_name: str) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _require_non_blank(value, field_name=field_name)
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return normalized_values


def _normalize_tags(tags: Sequence[str]) -> list[str]:
    normalized_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = tag.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_tags.append(normalized)
    return normalized_tags
