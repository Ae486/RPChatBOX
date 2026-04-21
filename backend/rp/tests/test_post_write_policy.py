"""Tests for post-write maintenance policy matching."""
from rp.models.post_write_policy import (
    PolicyDecision,
    PolicyRule,
    PostWriteMaintenancePolicy,
    build_balanced_policy,
)
from rp.services.post_write_apply_handler import PostWriteApplyHandler


def test_exact_policy_rule_match():
    handler = PostWriteApplyHandler()
    policy = PostWriteMaintenancePolicy(
        preset_id="test",
        rules=[
            PolicyRule(
                mode="longform",
                domain_pattern="scene.current.*",
                operation_kind="patch_fields",
                decision=PolicyDecision.NOTIFY_APPLY,
            )
        ],
    )

    decision = handler.decide(
        mode="longform",
        domain="scene",
        domain_path="scene.current.turn_state",
        operation_kind="patch_fields",
        policy=policy,
    )

    assert decision == PolicyDecision.NOTIFY_APPLY


def test_domain_path_fallback_to_coarse_domain():
    handler = PostWriteApplyHandler()
    policy = PostWriteMaintenancePolicy(
        preset_id="test",
        rules=[
            PolicyRule(
                mode="longform",
                domain_pattern="scene.*",
                operation_kind="patch_fields",
                decision=PolicyDecision.NOTIFY_APPLY,
            )
        ],
    )

    decision = handler.decide(
        mode="longform",
        domain="scene",
        domain_path=None,
        operation_kind="patch_fields",
        policy=policy,
    )

    assert decision == PolicyDecision.NOTIFY_APPLY


def test_unmatched_rule_falls_back_to_review_required():
    handler = PostWriteApplyHandler()

    decision = handler.decide(
        mode="longform",
        domain="scene",
        domain_path="scene.current",
        operation_kind="remove_record",
        policy=build_balanced_policy(),
    )

    assert decision == PolicyDecision.REVIEW_REQUIRED

