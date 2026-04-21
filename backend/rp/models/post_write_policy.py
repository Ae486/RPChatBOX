"""Post-write maintenance policy models for RP Phase A."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PolicyDecision(StrEnum):
    NOTIFY_APPLY = "notify_apply"
    REVIEW_REQUIRED = "review_required"
    SILENT = "silent"


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    domain_pattern: str
    operation_kind: str
    decision: PolicyDecision


class PostWriteMaintenancePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset_id: str
    rules: list[PolicyRule] = Field(default_factory=list)
    fallback_decision: PolicyDecision = PolicyDecision.REVIEW_REQUIRED


def build_conservative_policy() -> PostWriteMaintenancePolicy:
    """Return the MVP conservative preset."""
    rules = [
        PolicyRule(
            mode="longform",
            domain_pattern=pattern,
            operation_kind="*",
            decision=PolicyDecision.REVIEW_REQUIRED,
        )
        for pattern in (
            "foundation.*",
            "foreshadow_tracker.*",
            "relations.*",
            "goals.*",
        )
    ]
    return PostWriteMaintenancePolicy(preset_id="conservative", rules=rules)


def build_balanced_policy() -> PostWriteMaintenancePolicy:
    """Return the MVP balanced preset."""
    rules = [
        PolicyRule(
            mode="longform",
            domain_pattern="foundation.world.*",
            operation_kind="upsert_record",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="foundation.world.*",
            operation_kind="remove_record",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="foundation.character.*",
            operation_kind="upsert_record",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="foundation.character.*",
            operation_kind="remove_record",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="foundation.rule.*",
            operation_kind="upsert_record",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="foundation.rule.*",
            operation_kind="remove_record",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="foreshadow_tracker.*",
            operation_kind="*",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="relations.*",
            operation_kind="add_relation",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="relations.*",
            operation_kind="remove_relation",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="goals.*",
            operation_kind="upsert_record",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="goals.*",
            operation_kind="remove_record",
            decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="scene.current.*",
            operation_kind="patch_fields",
            decision=PolicyDecision.NOTIFY_APPLY,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="scene.closed.*",
            operation_kind="upsert_record",
            decision=PolicyDecision.NOTIFY_APPLY,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="character.voice_seed.*",
            operation_kind="patch_fields",
            decision=PolicyDecision.NOTIFY_APPLY,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="character.knowledge.*",
            operation_kind="patch_fields",
            decision=PolicyDecision.NOTIFY_APPLY,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="timeline.*",
            operation_kind="append_event",
            decision=PolicyDecision.NOTIFY_APPLY,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="inventory.*",
            operation_kind="patch_fields",
            decision=PolicyDecision.NOTIFY_APPLY,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="mechanics.*",
            operation_kind="patch_fields",
            decision=PolicyDecision.NOTIFY_APPLY,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="branch_state.*",
            operation_kind="patch_fields",
            decision=PolicyDecision.NOTIFY_APPLY,
        ),
        PolicyRule(
            mode="longform",
            domain_pattern="branch_state.*",
            operation_kind="set_status",
            decision=PolicyDecision.NOTIFY_APPLY,
        ),
    ]
    return PostWriteMaintenancePolicy(preset_id="balanced", rules=rules)

