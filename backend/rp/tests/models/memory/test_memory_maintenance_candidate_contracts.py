"""Tests for S3 memory maintenance candidate DTOs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rp.models.memory.maintenance_candidate import (
    MemoryMaintenanceCandidateBatch,
    MemoryMaintenanceOperation,
)


def test_candidate_batch_dumps_required_non_truth_contract_fields():
    batch = MemoryMaintenanceCandidateBatch.model_validate(
        {
            "schema_version": "s3a.memory-maintenance-candidate.v1",
            "worker_id": "longform_memory_worker",
            "phase": "post_write_maintenance",
            "candidates": [
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.frame",
                    "base_block_revision_id": "rev-scene-frame-1",
                    "operations": [
                        {
                            "kind": "append_item",
                            "content": "Lin Mo enters the north dock at dawn.",
                        }
                    ],
                    "source_refs": [
                        {
                            "source_type": "accepted_prose",
                            "source_id": "segment-1",
                        }
                    ],
                    "change_summary": "Record the new scene frame.",
                }
            ],
        }
    )

    dumped = batch.model_dump(mode="json")

    assert dumped["schema_version"] == "s3a.memory-maintenance-candidate.v1"
    assert dumped["worker_id"] == "longform_memory_worker"
    assert dumped["phase"] == "post_write_maintenance"
    assert dumped["candidates"][0]["target_domain"] == "current_scene"
    assert dumped["candidates"][0]["target_block_id"] == "scene.frame"
    assert dumped["candidates"][0]["base_block_revision_id"] == "rev-scene-frame-1"
    assert dumped["candidates"][0]["operations"][0]["field_id"] == "facts"
    assert dumped["candidates"][0]["source_refs"][0] == {
        "source_type": "accepted_prose",
        "source_id": "segment-1",
        "layer": None,
        "domain": None,
        "block_id": None,
        "entry_id": None,
        "revision": None,
        "metadata": {},
    }


def test_candidate_batch_rejects_unknown_extra_fields():
    with pytest.raises(ValidationError):
        MemoryMaintenanceCandidateBatch.model_validate(
            {
                "schema_version": "s3a.memory-maintenance-candidate.v1",
                "worker_id": "longform_memory_worker",
                "phase": "post_write_maintenance",
                "candidates": [
                    {
                        "target_domain": "current_scene",
                        "target_block_id": "scene.frame",
                        "base_block_revision_id": "rev-scene-frame-1",
                        "operations": [
                            {
                                "kind": "append_item",
                                "content": "A new fact.",
                            }
                        ],
                        "source_refs": [
                            {
                                "source_type": "accepted_prose",
                                "source_id": "segment-1",
                            }
                        ],
                        "change_summary": "Record the new scene frame.",
                    }
                ],
                "unexpected_policy": "silently-accepted",
            }
        )


def test_candidate_batch_rejects_empty_candidate_list():
    with pytest.raises(ValidationError):
        MemoryMaintenanceCandidateBatch.model_validate(
            {
                "schema_version": "s3a.memory-maintenance-candidate.v1",
                "worker_id": "longform_memory_worker",
                "phase": "post_write_maintenance",
                "candidates": [],
            }
        )


def test_candidate_rejects_unknown_extra_fields_inside_candidate_and_operation():
    with pytest.raises(ValidationError):
        MemoryMaintenanceCandidateBatch.model_validate(
            {
                "schema_version": "s3a.memory-maintenance-candidate.v1",
                "worker_id": "longform_memory_worker",
                "phase": "post_write_maintenance",
                "candidates": [
                    {
                        "target_domain": "current_scene",
                        "target_block_id": "scene.frame",
                        "base_block_revision_id": "rev-scene-frame-1",
                        "operations": [
                            {
                                "kind": "append_item",
                                "content": "A new fact.",
                                "priority": "hidden-extra-semantics",
                            }
                        ],
                        "source_refs": [
                            {
                                "source_type": "accepted_prose",
                                "source_id": "segment-1",
                            }
                        ],
                        "change_summary": "Record the new scene frame.",
                        "confidence": 0.9,
                    }
                ],
            }
        )


def test_operation_target_fact_id_and_handle_are_mutually_exclusive():
    with pytest.raises(ValidationError):
        MemoryMaintenanceOperation(
            kind="update_item",
            target_fact_id="fact-1",
            target_fact_handle="F1",
            content="Updated fact.",
        )
