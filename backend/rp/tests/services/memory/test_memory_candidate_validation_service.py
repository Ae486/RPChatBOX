"""Tests for S3 memory candidate validation."""

from __future__ import annotations

import pytest

from rp.services.memory.memory_candidate_validation_service import (
    MemoryCandidateValidationService,
)


def test_valid_append_update_remove_candidates_pass_without_mutating_registry():
    service = MemoryCandidateValidationService()
    before_domains = [
        domain.domain_id for domain in service._registry_service.list_domains()
    ]

    result = service.validate_batch(
        _batch(
            [
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.frame",
                    "base_block_revision_id": "rev-scene-frame-1",
                    "operations": [
                        {
                            "kind": "append_item",
                            "content": "Lin Mo reaches the north dock before dawn.",
                        },
                        {
                            "kind": "update_item",
                            "target_fact_id": "fact-scene-1",
                            "content": "The north dock is now under guard.",
                        },
                        {
                            "kind": "remove_item",
                            "target_fact_id": "fact-scene-2",
                        },
                    ],
                    "source_refs": _source_refs(),
                    "change_summary": "Maintain scene-frame facts from accepted prose.",
                }
            ]
        )
    )

    after_domains = [
        domain.domain_id for domain in service._registry_service.list_domains()
    ]

    assert result.accepted is True
    assert result.errors == []
    assert after_domains == before_domains


@pytest.mark.parametrize(
    ("operation_kind", "expected_code"),
    [
        ("create_domain", "memory_candidate_forbidden_schema_operation"),
        ("delete_domain", "memory_candidate_forbidden_schema_operation"),
        ("create_block", "memory_candidate_forbidden_schema_operation"),
        ("delete_block", "memory_candidate_forbidden_schema_operation"),
        ("create_field", "memory_candidate_forbidden_schema_operation"),
        ("delete_field", "memory_candidate_forbidden_schema_operation"),
        ("schema_change", "memory_candidate_forbidden_schema_operation"),
        ("change_schema", "memory_candidate_forbidden_schema_operation"),
        ("set_field", "memory_candidate_unsupported_operation"),
    ],
)
def test_validator_rejects_schema_and_unsupported_operations(
    operation_kind: str,
    expected_code: str,
):
    result = MemoryCandidateValidationService().validate_batch(
        _batch(
            [
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.frame",
                    "base_block_revision_id": "rev-scene-frame-1",
                    "operations": [
                        {
                            "kind": operation_kind,
                            "content": "Not allowed.",
                        }
                    ],
                    "source_refs": _source_refs(),
                    "change_summary": "Attempt an invalid operation.",
                }
            ]
        )
    )

    assert result.accepted is False
    assert [error.code for error in result.errors] == [expected_code]


def test_validator_rejects_non_facts_field_with_specific_error():
    result = MemoryCandidateValidationService().validate_batch(
        _batch(
            [
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.frame",
                    "base_block_revision_id": "rev-scene-frame-1",
                    "operations": [
                        {
                            "kind": "append_item",
                            "field_id": "schema",
                            "content": "Not a facts field.",
                        }
                    ],
                    "source_refs": _source_refs(),
                    "change_summary": "Attempt an invalid field write.",
                }
            ]
        )
    )

    assert result.accepted is False
    assert [error.code for error in result.errors] == [
        "memory_candidate_unsupported_field"
    ]


def test_validator_rejects_unknown_domain_and_block():
    service = MemoryCandidateValidationService()

    unknown_domain = service.validate_batch(
        _batch(
            [
                {
                    "target_domain": "scene",
                    "target_block_id": "scene.frame",
                    "base_block_revision_id": "rev-scene-frame-1",
                    "operations": [
                        {
                            "kind": "append_item",
                            "content": "Legacy domain should not be accepted.",
                        }
                    ],
                    "source_refs": _source_refs(),
                    "change_summary": "Use old bootstrap domain.",
                }
            ]
        )
    )
    unknown_block = service.validate_batch(
        _batch(
            [
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.unknown",
                    "base_block_revision_id": "rev-scene-frame-1",
                    "operations": [
                        {
                            "kind": "append_item",
                            "content": "Unknown block should not be accepted.",
                        }
                    ],
                    "source_refs": _source_refs(),
                    "change_summary": "Use unknown block.",
                }
            ]
        )
    )

    assert [error.code for error in unknown_domain.errors] == [
        "memory_candidate_unknown_target_domain"
    ]
    assert [error.code for error in unknown_block.errors] == [
        "memory_candidate_unknown_target_block"
    ]


def test_validator_rejects_missing_source_refs_and_base_revision():
    result = MemoryCandidateValidationService().validate_batch(
        _batch(
            [
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.frame",
                    "base_block_revision_id": None,
                    "operations": [
                        {
                            "kind": "append_item",
                            "content": "A new scene fact.",
                        }
                    ],
                    "source_refs": [],
                    "change_summary": "Missing governance refs.",
                }
            ]
        )
    )

    assert result.accepted is False
    assert {error.code for error in result.errors} == {
        "memory_candidate_missing_base_block_revision",
        "memory_candidate_missing_source_refs",
    }


def test_validator_rejects_contradictory_operations_on_same_fact():
    result = MemoryCandidateValidationService().validate_batch(
        _batch(
            [
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.frame",
                    "base_block_revision_id": "rev-scene-frame-1",
                    "operations": [
                        {
                            "kind": "update_item",
                            "target_fact_id": "fact-scene-1",
                            "content": "The dock is watched.",
                        },
                        {
                            "kind": "remove_item",
                            "target_fact_id": "fact-scene-1",
                        },
                    ],
                    "source_refs": _source_refs(),
                    "change_summary": "Contradict same fact.",
                }
            ]
        )
    )

    assert result.accepted is False
    assert [error.code for error in result.errors] == [
        "memory_candidate_contradictory_operations"
    ]


def test_validator_rejects_missing_update_or_remove_target():
    result = MemoryCandidateValidationService().validate_batch(
        _batch(
            [
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.frame",
                    "base_block_revision_id": "rev-scene-frame-1",
                    "operations": [
                        {
                            "kind": "update_item",
                            "content": "Cannot update without a fact target.",
                        },
                        {
                            "kind": "remove_item",
                        },
                    ],
                    "source_refs": _source_refs(),
                    "change_summary": "Missing target facts.",
                }
            ]
        )
    )

    assert result.accepted is False
    assert [error.code for error in result.errors] == [
        "memory_candidate_missing_target_fact",
        "memory_candidate_missing_target_fact",
    ]


def test_validator_rejects_append_targeting_existing_fact():
    result = MemoryCandidateValidationService().validate_batch(
        _batch(
            [
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.frame",
                    "base_block_revision_id": "rev-scene-frame-1",
                    "operations": [
                        {
                            "kind": "append_item",
                            "target_fact_id": "fact-scene-1",
                            "content": "Append must create a backend-owned fact.",
                        },
                    ],
                    "source_refs": _source_refs(),
                    "change_summary": "Attempt append with a preselected fact id.",
                }
            ]
        )
    )

    assert result.accepted is False
    assert [error.code for error in result.errors] == [
        "memory_candidate_append_targets_existing_fact"
    ]


def test_validator_rejects_candidate_schema_extra_fields():
    result = MemoryCandidateValidationService().validate_batch(
        {
            **_batch(
                [
                    {
                        "target_domain": "current_scene",
                        "target_block_id": "scene.frame",
                        "base_block_revision_id": "rev-scene-frame-1",
                        "operations": [
                            {
                                "kind": "append_item",
                                "content": "A new scene fact.",
                            }
                        ],
                        "source_refs": _source_refs(),
                        "change_summary": "Valid payload with one extra field.",
                    }
                ]
            ),
            "extra_semantics": True,
        }
    )

    assert result.accepted is False
    assert [error.code for error in result.errors] == [
        "memory_candidate_invalid_schema"
    ]


def _batch(candidates: list[dict]) -> dict:
    return {
        "schema_version": "s3a.memory-maintenance-candidate.v1",
        "worker_id": "longform_memory_worker",
        "phase": "post_write_maintenance",
        "candidates": candidates,
    }


def _source_refs() -> list[dict[str, str]]:
    return [
        {
            "source_type": "accepted_prose",
            "source_id": "segment-1",
        }
    ]
