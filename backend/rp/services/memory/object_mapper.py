"""Mappings for Phase E1 authoritative objects and settled projection slots."""

from __future__ import annotations

from dataclasses import dataclass

from rp.models.dsl import Domain, Layer, ObjectRef


@dataclass(frozen=True)
class AuthoritativeBinding:
    object_id: str
    domain: Domain
    domain_path: str
    backend_field: str


@dataclass(frozen=True)
class ProjectionBinding:
    summary_id: str
    domain: Domain
    domain_path: str
    slot_name: str


_AUTHORITATIVE_BY_OBJECT_ID: dict[str, AuthoritativeBinding] = {
    "chapter.current": AuthoritativeBinding(
        object_id="chapter.current",
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        backend_field="chapter_digest",
    ),
    "narrative_progress.current": AuthoritativeBinding(
        object_id="narrative_progress.current",
        domain=Domain.NARRATIVE_PROGRESS,
        domain_path="narrative_progress.current",
        backend_field="narrative_progress",
    ),
    "timeline.event_spine": AuthoritativeBinding(
        object_id="timeline.event_spine",
        domain=Domain.TIMELINE,
        domain_path="timeline.event_spine",
        backend_field="timeline_spine",
    ),
    "plot_thread.active": AuthoritativeBinding(
        object_id="plot_thread.active",
        domain=Domain.PLOT_THREAD,
        domain_path="plot_thread.active",
        backend_field="active_threads",
    ),
    "foreshadow.registry": AuthoritativeBinding(
        object_id="foreshadow.registry",
        domain=Domain.FORESHADOW,
        domain_path="foreshadow.registry",
        backend_field="foreshadow_registry",
    ),
    "character.state_digest": AuthoritativeBinding(
        object_id="character.state_digest",
        domain=Domain.CHARACTER,
        domain_path="character.state_digest",
        backend_field="character_state_digest",
    ),
}

_AUTHORITATIVE_DEFAULTS_BY_DOMAIN: dict[Domain, str] = {
    Domain.CHAPTER: "chapter.current",
    Domain.NARRATIVE_PROGRESS: "narrative_progress.current",
    Domain.TIMELINE: "timeline.event_spine",
    Domain.PLOT_THREAD: "plot_thread.active",
    Domain.FORESHADOW: "foreshadow.registry",
    Domain.CHARACTER: "character.state_digest",
}

_PROJECTION_BY_SUMMARY_ID: dict[str, ProjectionBinding] = {
    "projection.foundation_digest": ProjectionBinding(
        summary_id="projection.foundation_digest",
        domain=Domain.CHAPTER,
        domain_path="projection.foundation_digest",
        slot_name="foundation_digest",
    ),
    "projection.blueprint_digest": ProjectionBinding(
        summary_id="projection.blueprint_digest",
        domain=Domain.CHAPTER,
        domain_path="projection.blueprint_digest",
        slot_name="blueprint_digest",
    ),
    "projection.current_outline_digest": ProjectionBinding(
        summary_id="projection.current_outline_digest",
        domain=Domain.CHAPTER,
        domain_path="projection.current_outline_digest",
        slot_name="current_outline_digest",
    ),
    "projection.recent_segment_digest": ProjectionBinding(
        summary_id="projection.recent_segment_digest",
        domain=Domain.CHAPTER,
        domain_path="projection.recent_segment_digest",
        slot_name="recent_segment_digest",
    ),
    "projection.current_state_digest": ProjectionBinding(
        summary_id="projection.current_state_digest",
        domain=Domain.NARRATIVE_PROGRESS,
        domain_path="projection.current_state_digest",
        slot_name="current_state_digest",
    ),
}

_PROJECTION_ALIASES: dict[str, str] = {
    "foundation_digest": "projection.foundation_digest",
    "blueprint_digest": "projection.blueprint_digest",
    "current_outline_digest": "projection.current_outline_digest",
    "recent_segment_digest": "projection.recent_segment_digest",
    "current_state_digest": "projection.current_state_digest",
}

_PROJECTION_DEFAULTS_BY_DOMAIN: dict[Domain, list[str]] = {
    Domain.CHAPTER: [
        "projection.current_outline_digest",
        "projection.recent_segment_digest",
    ],
    Domain.NARRATIVE_PROGRESS: ["projection.current_state_digest"],
}


def authoritative_bindings() -> list[AuthoritativeBinding]:
    return list(_AUTHORITATIVE_BY_OBJECT_ID.values())


def projection_bindings() -> list[ProjectionBinding]:
    return list(_PROJECTION_BY_SUMMARY_ID.values())


def default_authoritative_ref_for_domain(
    domain: Domain,
    *,
    scope: str | None = None,
) -> ObjectRef:
    object_id = _AUTHORITATIVE_DEFAULTS_BY_DOMAIN.get(domain, f"{domain.value}.current")
    binding = _AUTHORITATIVE_BY_OBJECT_ID.get(object_id)
    domain_path = binding.domain_path if binding is not None else object_id
    return ObjectRef(
        object_id=object_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=domain,
        domain_path=domain_path,
        scope=scope,
        revision=1,
    )


def normalize_authoritative_ref(ref: ObjectRef) -> ObjectRef:
    binding = resolve_authoritative_binding(ref)
    if binding is None:
        return ref.model_copy(
            update={
                "domain_path": ref.domain_path or ref.object_id,
                "revision": ref.revision or 1,
            }
        )
    return ref.model_copy(
        update={
            "layer": Layer.CORE_STATE_AUTHORITATIVE,
            "domain": binding.domain,
            "domain_path": binding.domain_path,
            "revision": ref.revision or 1,
        }
    )


def resolve_authoritative_binding(ref: ObjectRef) -> AuthoritativeBinding | None:
    if ref.layer != Layer.CORE_STATE_AUTHORITATIVE:
        return None
    if ref.object_id in _AUTHORITATIVE_BY_OBJECT_ID:
        return _AUTHORITATIVE_BY_OBJECT_ID[ref.object_id]
    if ref.domain_path and ref.domain_path in _AUTHORITATIVE_BY_OBJECT_ID:
        return _AUTHORITATIVE_BY_OBJECT_ID[ref.domain_path]
    default_object_id = _AUTHORITATIVE_DEFAULTS_BY_DOMAIN.get(ref.domain)
    if default_object_id and (
        ref.object_id == f"{ref.domain.value}.current"
        or ref.domain_path == f"{ref.domain.value}.current"
    ):
        return _AUTHORITATIVE_BY_OBJECT_ID[default_object_id]
    return None


def projection_summary_ids_for_domain(domain: Domain) -> list[str]:
    return list(_PROJECTION_DEFAULTS_BY_DOMAIN.get(domain, []))


def normalize_projection_summary_id(summary_id: str) -> str:
    return _PROJECTION_ALIASES.get(summary_id, summary_id)


def resolve_projection_binding(summary_id: str) -> ProjectionBinding | None:
    return _PROJECTION_BY_SUMMARY_ID.get(normalize_projection_summary_id(summary_id))
