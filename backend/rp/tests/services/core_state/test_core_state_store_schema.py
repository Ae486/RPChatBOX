"""Tests for formal Core State store schema registration."""

from __future__ import annotations

from sqlalchemy import inspect


def test_core_state_store_tables_are_created(retrieval_session):
    inspector = inspect(retrieval_session.get_bind())
    tables = set(inspector.get_table_names())

    assert "rp_core_state_authoritative_objects" in tables
    assert "rp_core_state_authoritative_revisions" in tables
    assert "rp_core_state_projection_slots" in tables
    assert "rp_core_state_projection_slot_revisions" in tables
    assert "rp_memory_apply_target_links" in tables


def test_memory_apply_receipts_have_phase_g_backend_column(retrieval_session):
    inspector = inspect(retrieval_session.get_bind())
    columns = {item["name"] for item in inspector.get_columns("rp_memory_apply_receipts")}

    assert "apply_backend" in columns

