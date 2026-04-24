"""Convert legacy bundle.state_patch_proposals into canonical proposal inputs."""

from __future__ import annotations

from typing import Any

from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import AppendEventOp, PatchFieldsOp, ProposalSubmitInput


class LegacyStatePatchProposalBuilder:
    """Build canonical proposal inputs from the current legacy patch dict shape."""

    _PATCH_TARGETS: dict[str, tuple[Domain, str]] = {
        "chapter_digest": (Domain.CHAPTER, "chapter.current"),
        "narrative_progress": (Domain.NARRATIVE_PROGRESS, "narrative_progress.current"),
        "character_state_digest": (Domain.CHARACTER, "character.state_digest"),
    }

    _APPEND_TARGETS: dict[str, tuple[Domain, str]] = {
        "timeline_spine": (Domain.TIMELINE, "timeline.event_spine"),
        "active_threads": (Domain.PLOT_THREAD, "plot_thread.active"),
        "foreshadow_registry": (Domain.FORESHADOW, "foreshadow.registry"),
    }

    def build_inputs(
        self,
        *,
        story_id: str,
        mode: str,
        patch: dict[str, Any],
    ) -> list[ProposalSubmitInput]:
        proposal_inputs: list[ProposalSubmitInput] = []
        for field_name, value in patch.items():
            if field_name in self._PATCH_TARGETS:
                if not isinstance(value, dict):
                    raise ValueError(f"phase_e_legacy_patch_shape_unsupported:{field_name}")
                domain, object_id = self._PATCH_TARGETS[field_name]
                proposal_inputs.append(
                    ProposalSubmitInput(
                        story_id=story_id,
                        mode=mode,
                        domain=domain,
                        domain_path=object_id,
                        operations=[
                            PatchFieldsOp(
                                target_ref=ObjectRef(
                                    object_id=object_id,
                                    layer=Layer.CORE_STATE_AUTHORITATIVE,
                                    domain=domain,
                                    domain_path=object_id,
                                ),
                                field_patch=dict(value),
                            )
                        ],
                        reason=f"legacy_bundle_patch:{field_name}",
                    )
                )
                continue
            if field_name in self._APPEND_TARGETS:
                if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                    raise ValueError(f"phase_e_legacy_patch_shape_unsupported:{field_name}")
                domain, object_id = self._APPEND_TARGETS[field_name]
                proposal_inputs.append(
                    ProposalSubmitInput(
                        story_id=story_id,
                        mode=mode,
                        domain=domain,
                        domain_path=object_id,
                        operations=[
                            AppendEventOp(
                                target_ref=ObjectRef(
                                    object_id=object_id,
                                    layer=Layer.CORE_STATE_AUTHORITATIVE,
                                    domain=domain,
                                    domain_path=object_id,
                                ),
                                event_data=dict(item),
                            )
                            for item in value
                        ],
                        reason=f"legacy_bundle_patch:{field_name}",
                    )
                )
                continue
            raise ValueError(f"phase_e_legacy_patch_field_unsupported:{field_name}")
        return proposal_inputs
