"""Mode-extension contracts for roleplay/TRPG runtime slots."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind

CHARACTER_MEMORY_WORKER_ID = "CharacterMemoryWorker"
SCENE_INTERACTION_WORKER_ID = "SceneInteractionWorker"
RULE_STATE_WORKER_ID = "RuleStateWorker"

RULE_CARD_SLOT_ID = "rule_card"
RULE_STATE_CARD_SLOT_ID = "rule_state_card"
CHARACTER_LOCAL_MEMORY_SLOT_ID = "character_local_memory"
KNOWLEDGE_BOUNDARY_SLOT_ID = "knowledge_boundary_refs"
SCENE_INTENT_SLOT_ID = "scene_intent"
PARTICIPANT_INTENT_SLOT_ID = "participant_intent"


class RuntimeModeExtensionSlotKind(StrEnum):
    """Typed extension-slot kinds compiled into the snapshot."""

    WORKER = "worker"
    WORKSPACE_MATERIAL = "workspace_material"
    PACKET_SIDECAR = "packet_sidecar"
    POLICY = "policy"


class InteractiveAcceptanceSignal(StrEnum):
    """Interactive-mode acceptance signals frozen into snapshot policy."""

    NEXT_USER_MESSAGE = "next_user_message"


class RuntimeModeExtensionSlot(BaseModel):
    """Declarative mode extension slot compiled into runtime snapshot policy."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["longform", "roleplay", "trpg"]
    slot_id: str
    slot_kind: RuntimeModeExtensionSlotKind
    descriptor_ref: str
    enabled_by_default: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slot_id", "descriptor_ref")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name or 'value'} must be non-empty")
        return normalized


class InteractiveModeAcceptancePolicy(BaseModel):
    """Interactive roleplay/TRPG acceptance policy pinned in one snapshot."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["roleplay", "trpg"]
    acceptance_signal: InteractiveAcceptanceSignal = (
        InteractiveAcceptanceSignal.NEXT_USER_MESSAGE
    )
    create_longform_adoption_receipt: bool = False
    hard_rule_state_gate: bool = False
    allow_pending_deferred_continuation: bool = True


class RuleCardMaterial(BaseModel):
    """Typed sidecar payload for TRPG rule cards kept in Runtime Workspace."""

    model_config = ConfigDict(extra="forbid")

    material_id: str
    identity: MemoryRuntimeIdentity
    rule_refs: list[str] = Field(default_factory=list)
    adjudication_summary: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("material_id")
    @classmethod
    def _require_material_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("material_id must be non-empty")
        return normalized


class RuleStateCardMaterial(BaseModel):
    """Typed sidecar payload for TRPG mechanics state cards."""

    model_config = ConfigDict(extra="forbid")

    material_id: str
    identity: MemoryRuntimeIdentity
    mechanics_state_patch: dict[str, Any] = Field(default_factory=dict)
    status_effects: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("material_id")
    @classmethod
    def _require_material_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("material_id must be non-empty")
        return normalized


class ModeExtensionProfile(BaseModel):
    """Compiled mode-extension profile stored under snapshot mode settings."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["roleplay", "trpg"]
    slots: list[RuntimeModeExtensionSlot] = Field(default_factory=list)
    acceptance_policy: InteractiveModeAcceptancePolicy


def build_mode_extension_profile(mode: str) -> ModeExtensionProfile | None:
    """Return the frozen extension profile for an interactive mode."""

    normalized_mode = mode.strip().lower()
    if normalized_mode == "roleplay":
        return ModeExtensionProfile(
            mode="roleplay",
            slots=[
                RuntimeModeExtensionSlot(
                    mode="roleplay",
                    slot_id="character_memory_worker",
                    slot_kind=RuntimeModeExtensionSlotKind.WORKER,
                    descriptor_ref=f"runtime_worker:{CHARACTER_MEMORY_WORKER_ID}",
                    enabled_by_default=True,
                    metadata_json={"owned_domains": ["character", "relation"]},
                ),
                RuntimeModeExtensionSlot(
                    mode="roleplay",
                    slot_id="scene_interaction_worker",
                    slot_kind=RuntimeModeExtensionSlotKind.WORKER,
                    descriptor_ref=f"runtime_worker:{SCENE_INTERACTION_WORKER_ID}",
                    enabled_by_default=True,
                    metadata_json={"owned_domains": ["scene", "goal"]},
                ),
                RuntimeModeExtensionSlot(
                    mode="roleplay",
                    slot_id=CHARACTER_LOCAL_MEMORY_SLOT_ID,
                    slot_kind=RuntimeModeExtensionSlotKind.PACKET_SIDECAR,
                    descriptor_ref=f"packet_sidecar:{CHARACTER_LOCAL_MEMORY_SLOT_ID}",
                    enabled_by_default=False,
                ),
                RuntimeModeExtensionSlot(
                    mode="roleplay",
                    slot_id=KNOWLEDGE_BOUNDARY_SLOT_ID,
                    slot_kind=RuntimeModeExtensionSlotKind.PACKET_SIDECAR,
                    descriptor_ref=f"packet_sidecar:{KNOWLEDGE_BOUNDARY_SLOT_ID}",
                    enabled_by_default=False,
                ),
                RuntimeModeExtensionSlot(
                    mode="roleplay",
                    slot_id=SCENE_INTENT_SLOT_ID,
                    slot_kind=RuntimeModeExtensionSlotKind.PACKET_SIDECAR,
                    descriptor_ref=f"packet_sidecar:{SCENE_INTENT_SLOT_ID}",
                    enabled_by_default=False,
                ),
                RuntimeModeExtensionSlot(
                    mode="roleplay",
                    slot_id=PARTICIPANT_INTENT_SLOT_ID,
                    slot_kind=RuntimeModeExtensionSlotKind.PACKET_SIDECAR,
                    descriptor_ref=f"packet_sidecar:{PARTICIPANT_INTENT_SLOT_ID}",
                    enabled_by_default=False,
                ),
                RuntimeModeExtensionSlot(
                    mode="roleplay",
                    slot_id="interactive_acceptance",
                    slot_kind=RuntimeModeExtensionSlotKind.POLICY,
                    descriptor_ref="policy:interactive_acceptance",
                    enabled_by_default=True,
                    metadata_json={
                        "acceptance_signal": InteractiveAcceptanceSignal.NEXT_USER_MESSAGE.value
                    },
                ),
            ],
            acceptance_policy=InteractiveModeAcceptancePolicy(mode="roleplay"),
        )
    if normalized_mode == "trpg":
        return ModeExtensionProfile(
            mode="trpg",
            slots=[
                RuntimeModeExtensionSlot(
                    mode="trpg",
                    slot_id="rule_state_worker",
                    slot_kind=RuntimeModeExtensionSlotKind.WORKER,
                    descriptor_ref=f"runtime_worker:{RULE_STATE_WORKER_ID}",
                    enabled_by_default=True,
                    metadata_json={"owned_domains": ["rule_state", "inventory", "world_rule"]},
                ),
                RuntimeModeExtensionSlot(
                    mode="trpg",
                    slot_id=RULE_CARD_SLOT_ID,
                    slot_kind=RuntimeModeExtensionSlotKind.WORKSPACE_MATERIAL,
                    descriptor_ref=f"workspace_material:{RuntimeWorkspaceMaterialKind.RULE_CARD.value}",
                    enabled_by_default=True,
                ),
                RuntimeModeExtensionSlot(
                    mode="trpg",
                    slot_id=RULE_STATE_CARD_SLOT_ID,
                    slot_kind=RuntimeModeExtensionSlotKind.WORKSPACE_MATERIAL,
                    descriptor_ref=f"workspace_material:{RuntimeWorkspaceMaterialKind.RULE_STATE_CARD.value}",
                    enabled_by_default=True,
                ),
                RuntimeModeExtensionSlot(
                    mode="trpg",
                    slot_id=RULE_CARD_SLOT_ID,
                    slot_kind=RuntimeModeExtensionSlotKind.PACKET_SIDECAR,
                    descriptor_ref=f"packet_sidecar:{RULE_CARD_SLOT_ID}",
                    enabled_by_default=True,
                ),
                RuntimeModeExtensionSlot(
                    mode="trpg",
                    slot_id=RULE_STATE_CARD_SLOT_ID,
                    slot_kind=RuntimeModeExtensionSlotKind.PACKET_SIDECAR,
                    descriptor_ref=f"packet_sidecar:{RULE_STATE_CARD_SLOT_ID}",
                    enabled_by_default=True,
                ),
                RuntimeModeExtensionSlot(
                    mode="trpg",
                    slot_id="interactive_acceptance",
                    slot_kind=RuntimeModeExtensionSlotKind.POLICY,
                    descriptor_ref="policy:interactive_acceptance",
                    enabled_by_default=True,
                    metadata_json={
                        "acceptance_signal": InteractiveAcceptanceSignal.NEXT_USER_MESSAGE.value,
                        "hard_rule_state_gate": True,
                    },
                ),
            ],
            acceptance_policy=InteractiveModeAcceptancePolicy(
                mode="trpg",
                hard_rule_state_gate=True,
                allow_pending_deferred_continuation=False,
            ),
        )
    return None


def packet_sidecar_slot_ids_for_profile(
    profile: ModeExtensionProfile | None,
) -> list[str]:
    """Return enabled packet-sidecar slot ids for one extension profile."""

    if profile is None:
        return []
    return [
        slot.slot_id
        for slot in profile.slots
        if slot.slot_kind == RuntimeModeExtensionSlotKind.PACKET_SIDECAR
        and slot.enabled_by_default
    ]


def worker_slot_ids_for_profile(profile: ModeExtensionProfile | None) -> list[str]:
    """Return runtime worker ids declared by the extension profile."""

    if profile is None:
        return []
    worker_ids: list[str] = []
    for slot in profile.slots:
        if (
            slot.slot_kind == RuntimeModeExtensionSlotKind.WORKER
            and slot.descriptor_ref.startswith("runtime_worker:")
        ):
            worker_ids.append(slot.descriptor_ref.split(":", 1)[1])
    return worker_ids


def workspace_material_slot_ids_for_profile(
    profile: ModeExtensionProfile | None,
) -> list[str]:
    """Return workspace-material slot ids declared by the extension profile."""

    if profile is None:
        return []
    return [
        slot.slot_id
        for slot in profile.slots
        if slot.slot_kind == RuntimeModeExtensionSlotKind.WORKSPACE_MATERIAL
        and slot.enabled_by_default
    ]


def packet_sidecar_material_kinds_for_slot(
    slot_id: str,
) -> list[RuntimeWorkspaceMaterialKind]:
    """Resolve packet-sidecar slot ids into Runtime Workspace material kinds."""

    normalized_slot = slot_id.strip().lower()
    if normalized_slot == RULE_CARD_SLOT_ID:
        return [RuntimeWorkspaceMaterialKind.RULE_CARD]
    if normalized_slot == RULE_STATE_CARD_SLOT_ID:
        return [RuntimeWorkspaceMaterialKind.RULE_STATE_CARD]
    return []
