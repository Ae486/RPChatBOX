"""API tests for SetupAgent MVP setup workspace flows."""
from __future__ import annotations

from sqlmodel import Session, select

from models.rp_retrieval_store import KnowledgeChunkRecord, SourceAssetRecord
from services.database import get_engine


def _create_workspace(client) -> str:
    response = client.post(
        "/api/rp/setup/workspaces",
        json={"story_id": "story_setup_mvp", "mode": "longform"},
    )
    assert response.status_code == 201
    return response.json()["workspace_id"]


def test_setup_workspace_patch_and_step_context_flow(client):
    workspace_id = _create_workspace(client)

    response = client.patch(
        f"/api/rp/setup/workspaces/{workspace_id}/story-config",
        json={
            "model_profile_ref": "model.default",
            "retrieval_embedding_model_id": "embedding-model-a",
            "retrieval_embedding_provider_id": "provider-embedding",
            "retrieval_rerank_model_id": "rerank-model-a",
            "retrieval_rerank_provider_id": "provider-rerank",
            "notes": "Use balanced preset",
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    workspace_payload = client.get(f"/api/rp/setup/workspaces/{workspace_id}").json()
    assert workspace_payload["story_config_draft"]["retrieval_embedding_model_id"] == "embedding-model-a"
    assert workspace_payload["story_config_draft"]["retrieval_rerank_model_id"] == "rerank-model-a"

    response = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/foundation/entries",
        json={
            "entry_id": "world_city_1",
            "domain": "world",
            "path": "city.rivergate",
            "title": "Rivergate",
            "tags": ["city", "trade"],
            "source_refs": ["asset:worldbook"],
            "content": {"summary": "Rivergate controls the eastern ferry route."},
        },
    )
    assert response.status_code == 200
    assert response.json()["updated_refs"] == ["foundation:world_city_1"]

    response = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/assets",
        json={
            "step_id": "foundation",
            "asset_kind": "worldbook",
            "source_ref": "/tmp/worldbook.md",
            "title": "Worldbook",
            "parse_status": "parsed",
            "parsed_payload": {
                "sections": [
                    {
                        "section_id": "sec-1",
                        "title": "River District",
                        "path": "foundation.world.river_district",
                        "level": 1,
                        "text": "River District forbids open flame rituals.",
                        "tags": ["district"],
                    }
                ]
            },
            "mapped_targets": ["foundation"],
        },
    )
    assert response.status_code == 200
    asset_ref = response.json()["updated_refs"][0]
    assert asset_ref.startswith("asset:")

    response = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/step-context",
        json={
            "current_step": "foundation",
            "user_prompt": "整理世界观基础设定",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["current_step"] == "foundation"
    assert payload["current_draft_snapshot"]["entries"][0]["entry_id"] == "world_city_1"
    assert payload["step_asset_preview"][0]["parse_status"] == "parsed"
    assert payload["user_prompt"] == "整理世界观基础设定"


def test_setup_commit_ingestion_and_activation_check(client):
    workspace_id = _create_workspace(client)

    assert client.patch(
        f"/api/rp/setup/workspaces/{workspace_id}/story-config",
        json={
            "model_profile_ref": "model.default",
            "worker_profile_ref": "worker.default",
            "post_write_policy_preset": "balanced",
            "retrieval_embedding_model_id": "embedding-model-a",
            "retrieval_embedding_provider_id": "provider-embedding",
            "retrieval_rerank_model_id": "rerank-model-a",
            "retrieval_rerank_provider_id": "provider-rerank",
        },
    ).status_code == 200
    assert client.patch(
        f"/api/rp/setup/workspaces/{workspace_id}/writing-contract",
        json={
            "pov_rules": ["third_person_limited"],
            "style_rules": ["restrained", "lean"],
            "writing_constraints": ["avoid exposition dumps"],
        },
    ).status_code == 200
    assert client.patch(
        f"/api/rp/setup/workspaces/{workspace_id}/longform-blueprint",
        json={
            "premise": "A courier discovers the city archive is a prison key registry.",
            "central_conflict": "The courier must expose the registry before the purge.",
            "chapter_blueprints": [
                {
                    "chapter_id": "ch1",
                    "title": "The Ledger",
                    "purpose": "Reveal the first key.",
                    "major_beats": ["Discovery", "Escape"],
                    "setup_payoff_targets": ["archive key"],
                }
            ],
        },
    ).status_code == 200
    assert client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/foundation/entries",
        json={
            "entry_id": "character_courier",
            "domain": "character",
            "path": "cast.courier",
            "title": "Courier",
            "tags": ["protagonist"],
            "source_refs": [],
            "content": {"summary": "The courier remembers every lock pattern after one glance."},
        },
    ).status_code == 200
    assert client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/assets",
        json={
            "step_id": "foundation",
            "asset_kind": "character_card",
            "source_ref": "/tmp/courier.md",
            "title": "Courier Card",
            "parse_status": "parsed",
            "parsed_payload": {
                "sections": [
                    {
                        "section_id": "sec-1",
                        "title": "Voice",
                        "path": "character.voice_seed.courier",
                        "level": 1,
                        "text": "The courier answers in short observations and concrete details.",
                        "tags": ["voice"],
                    }
                ]
            },
            "mapped_targets": ["character"],
        },
    ).status_code == 200

    for step_id in ("story_config", "writing_contract", "foundation", "longform_blueprint"):
        response = client.post(
            f"/api/rp/setup/workspaces/{workspace_id}/commit-proposals",
            json={
                "step_id": step_id,
                "target_draft_refs": [f"draft:{step_id}"],
                "reason": f"freeze {step_id}",
            },
        )
        assert response.status_code == 200
        proposal_ref = response.json()["updated_refs"][0]
        proposal_id = proposal_ref.split("proposal:", 1)[1]
        response = client.post(
            f"/api/rp/setup/workspaces/{workspace_id}/commit-proposals/{proposal_id}/accept"
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    response = client.post(f"/api/rp/setup/workspaces/{workspace_id}/activation-check")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["handoff"]["workspace_id"] == workspace_id
    assert payload["handoff"]["blueprint_commit_ref"] is not None
    assert payload["handoff"]["foundation_commit_refs"]
    assert payload["handoff"]["archival_ready_refs"]
    assert payload["handoff"]["runtime_story_config"]["retrieval_embedding_model_id"] == "embedding-model-a"
    assert payload["handoff"]["runtime_story_config"]["retrieval_rerank_model_id"] == "rerank-model-a"

    workspace = client.get(f"/api/rp/setup/workspaces/{workspace_id}").json()
    assert workspace["workspace_state"] == "ready_to_activate"
    assert all(
        job["state"] == "completed" for job in workspace["retrieval_ingestion_jobs"]
    )

    with Session(get_engine()) as session:
        chunk_count = session.exec(select(KnowledgeChunkRecord)).all()
        assets = session.exec(select(SourceAssetRecord)).all()

    assert len(chunk_count) >= 2
    assert len(assets) >= 2
