"""Tests for RP shared DSL models."""
from rp.models.dsl import Domain, Layer, ObjectRef, TypedEnvelope


def test_typed_envelope_canonical_dump_excludes_none():
    envelope = TypedEnvelope[dict](
        type="runtime.proposal.state_patch",
        payload={"ok": True},
    )

    assert envelope.canonical_dump() == {
        "schema_version": "1.0",
        "type": "runtime.proposal.state_patch",
        "scope": {},
        "producer": {},
        "refs": {},
        "payload": {"ok": True},
    }


def test_object_ref_serializes_enum_values():
    ref = ObjectRef(
        object_id="scene.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.SCENE,
        domain_path="scene.current",
        revision=2,
    )

    assert ref.model_dump(mode="json") == {
        "object_id": "scene.current",
        "layer": "core_state.authoritative",
        "domain": "scene",
        "domain_path": "scene.current",
        "scope": None,
        "revision": 2,
    }

