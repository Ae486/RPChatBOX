"""Integration tests for active-story longform MVP APIs."""

from __future__ import annotations

import json

from sqlmodel import Session as SqlSession

from config import get_settings
from rp.models.dsl import Domain, Layer
from rp.models.memory_crud import ProposalSubmitInput
from rp.models.story_runtime import (
    LongformChapterPhase,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService
from services.database import get_engine


def teardown_function(_function) -> None:
    get_settings.cache_clear()


def _provider_payload(provider_id: str = "provider-story"):
    return {
        "id": provider_id,
        "name": "OpenAI",
        "type": "openai",
        "api_key": "sk-test-12345678",
        "api_url": "https://api.openai.com/v1",
        "custom_headers": {},
        "is_enabled": True,
    }


def _model_payload(model_id: str = "model-story"):
    return {
        "id": model_id,
        "provider_id": "provider-story",
        "model_name": "gpt-4o-mini",
        "display_name": "GPT-4o Mini",
        "capabilities": ["text", "tool"],
        "default_params": {
            "temperature": 0.7,
            "max_tokens": 2048,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
            "stream_output": True,
        },
        "is_enabled": True,
        "description": "story test model",
    }


def _seed_formal_memory_block_session() -> dict[str, str]:
    with SqlSession(get_engine()) as db_session:
        story_session_service = StorySessionService(db_session)
        story_session = story_session_service.create_session(
            story_id="story-api-block-read",
            source_workspace_id="workspace-api-block-read",
            mode="longform",
            runtime_story_config={},
            writer_contract={},
            current_state_json={
                "chapter_digest": {"title": "Mirror API Chapter"},
                "narrative_progress": {
                    "current_phase": "outline_drafting",
                    "accepted_segments": 0,
                },
                "timeline_spine": [],
                "active_threads": [],
                "foreshadow_registry": [],
                "character_state_digest": {},
            },
            initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
        )
        chapter = story_session_service.create_chapter_workspace(
            session_id=story_session.session_id,
            chapter_index=1,
            phase=LongformChapterPhase.OUTLINE_DRAFTING,
            builder_snapshot_json={
                "foundation_digest": ["Mirror API foundation"],
                "blueprint_digest": ["Mirror API blueprint"],
                "current_outline_digest": ["Mirror API outline"],
                "recent_segment_digest": ["Mirror API segment"],
                "current_state_digest": ["Mirror API state"],
            },
        )
        core_repo = CoreStateStoreRepository(db_session)
        authoritative_row = core_repo.upsert_authoritative_object(
            story_id=story_session.story_id,
            session_id=story_session.session_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            domain=Domain.CHAPTER.value,
            domain_path="chapter.current",
            object_id="chapter.current",
            scope="story",
            current_revision=5,
            data_json={"current_chapter": 1, "title": "Formal API Chapter"},
            metadata_json={"test_marker": "api_formal_authoritative"},
            latest_apply_id="apply-api-formal",
            payload_schema_ref="schema://core-state/api-chapter-current",
        )
        core_repo.upsert_authoritative_revision(
            authoritative_object_id=authoritative_row.authoritative_object_id,
            story_id=story_session.story_id,
            session_id=story_session.session_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            domain=Domain.CHAPTER.value,
            domain_path="chapter.current",
            object_id="chapter.current",
            scope="story",
            revision=5,
            data_json={"current_chapter": 1, "title": "Formal API Chapter"},
            revision_source_kind="api_test",
            source_apply_id="apply-api-formal",
            metadata_json={"test_marker": "api_formal_authoritative_revision"},
        )
        projection_row = core_repo.upsert_projection_slot(
            story_id=story_session.story_id,
            session_id=story_session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            layer=Layer.CORE_STATE_PROJECTION.value,
            domain=Domain.CHAPTER.value,
            domain_path="projection.current_outline_digest",
            summary_id="projection.current_outline_digest",
            slot_name="current_outline_digest",
            scope="chapter",
            current_revision=6,
            items_json=["Formal API outline"],
            metadata_json={"test_marker": "api_formal_projection"},
            last_refresh_kind="api_test_refresh",
            payload_schema_ref="schema://core-state/api-projection-slot",
        )
        core_repo.upsert_projection_slot_revision(
            projection_slot_id=projection_row.projection_slot_id,
            story_id=story_session.story_id,
            session_id=story_session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            layer=Layer.CORE_STATE_PROJECTION.value,
            domain=Domain.CHAPTER.value,
            domain_path="projection.current_outline_digest",
            summary_id="projection.current_outline_digest",
            slot_name="current_outline_digest",
            scope="chapter",
            revision=6,
            items_json=["Formal API outline"],
            refresh_source_kind="api_test_refresh",
            refresh_source_ref="artifact:outline",
            metadata_json={"test_marker": "api_formal_projection_revision"},
        )
        proposal_repo = ProposalRepository(db_session)
        matching_review_required = proposal_repo.create_proposal(
            input_model=ProposalSubmitInput(
                story_id=story_session.story_id,
                mode="longform",
                domain=Domain.CHAPTER,
                domain_path="chapter.current",
                operations=[
                    {
                        "kind": "patch_fields",
                        "target_ref": {
                            "object_id": "chapter.current",
                            "layer": Layer.CORE_STATE_AUTHORITATIVE,
                            "domain": Domain.CHAPTER,
                            "domain_path": "chapter.current",
                        },
                        "field_patch": {"title": "Pending API Chapter"},
                    }
                ],
                base_refs=[
                    {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                        "scope": "story",
                        "revision": 5,
                    }
                ],
                reason="api review required detail",
                trace_id="trace-api-review-required",
            ),
            status="review_required",
            policy_decision="review_required",
            submit_source="api_test",
            session_id=story_session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
        )
        matching_applied = proposal_repo.create_proposal(
            input_model=ProposalSubmitInput(
                story_id=story_session.story_id,
                mode="longform",
                domain=Domain.CHAPTER,
                domain_path="chapter.current",
                operations=[
                    {
                        "kind": "patch_fields",
                        "target_ref": {
                            "object_id": "chapter.current",
                            "layer": Layer.CORE_STATE_AUTHORITATIVE,
                            "domain": Domain.CHAPTER,
                            "domain_path": "chapter.current",
                        },
                        "field_patch": {"title": "Applied API Chapter"},
                    }
                ],
                base_refs=[
                    {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                        "scope": "story",
                        "revision": 5,
                    }
                ],
                reason="api applied detail",
                trace_id="trace-api-applied",
            ),
            status="review_required",
            policy_decision="review_required",
            submit_source="api_test",
            session_id=story_session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
        )
        proposal_apply_service = ProposalApplyService(
            story_session_service=story_session_service,
            proposal_repository=proposal_repo,
            story_state_apply_service=StoryStateApplyService(),
        )
        proposal_apply_service.apply_proposal(matching_applied.proposal_id)
        same_domain_other_block = proposal_repo.create_proposal(
            input_model=ProposalSubmitInput(
                story_id=story_session.story_id,
                mode="longform",
                domain=Domain.CHAPTER,
                domain_path="chapter.unrelated",
                operations=[
                    {
                        "kind": "patch_fields",
                        "target_ref": {
                            "object_id": "chapter.unrelated",
                            "layer": Layer.CORE_STATE_AUTHORITATIVE,
                            "domain": Domain.CHAPTER,
                            "domain_path": "chapter.unrelated",
                        },
                        "field_patch": {"title": "Wrong API Block"},
                    }
                ],
            ),
            status="pending",
            policy_decision="review_required",
            submit_source="api_test",
            session_id=story_session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
        )
        projection_target = proposal_repo.create_proposal(
            input_model=ProposalSubmitInput(
                story_id=story_session.story_id,
                mode="longform",
                domain=Domain.CHAPTER,
                domain_path="projection.current_outline_digest",
                operations=[
                    {
                        "kind": "patch_fields",
                        "target_ref": {
                            "object_id": "projection.current_outline_digest",
                            "layer": Layer.CORE_STATE_PROJECTION,
                            "domain": Domain.CHAPTER,
                            "domain_path": "projection.current_outline_digest",
                        },
                        "field_patch": {"items": ["Projection proposal"]},
                    }
                ],
            ),
            status="pending",
            policy_decision="review_required",
            submit_source="api_test",
            session_id=story_session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
        )
        runtime_artifact = story_session_service.create_artifact(
            session_id=story_session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            artifact_kind=StoryArtifactKind.STORY_SEGMENT,
            status=StoryArtifactStatus.DRAFT,
            content_text="Runtime API draft segment",
            metadata={"command_kind": "write_next_segment"},
            revision=2,
        )
        accepted_runtime_artifact = story_session_service.create_artifact(
            session_id=story_session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            artifact_kind=StoryArtifactKind.STORY_SEGMENT,
            status=StoryArtifactStatus.ACCEPTED,
            content_text="Accepted runtime artifact should stay outside runtime blocks",
            metadata={"command_kind": "accept_pending_segment"},
            revision=3,
        )
        runtime_discussion_entry = story_session_service.create_discussion_entry(
            session_id=story_session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            role="assistant",
            content_text="The escape needs more urgency.",
            linked_artifact_id=runtime_artifact.artifact_id,
        )
        result = {
            "session_id": story_session.session_id,
            "authoritative_block_id": authoritative_row.authoritative_object_id,
            "projection_block_id": projection_row.projection_slot_id,
            "runtime_artifact_block_id": (
                f"runtime_workspace:artifact:{runtime_artifact.artifact_id}"
            ),
            "runtime_discussion_block_id": (
                f"runtime_workspace:discussion:{runtime_discussion_entry.entry_id}"
            ),
            "accepted_runtime_artifact_id": accepted_runtime_artifact.artifact_id,
            "matching_review_required_proposal_id": matching_review_required.proposal_id,
            "matching_applied_proposal_id": matching_applied.proposal_id,
            "same_domain_other_proposal_id": same_domain_other_block.proposal_id,
            "projection_target_proposal_id": projection_target.proposal_id,
        }
        db_session.commit()
        return result


def _authoritative_block_patch_payload(*, title: str, domain: str = "chapter") -> dict:
    return {
        "operations": [
            {
                "kind": "patch_fields",
                "target_ref": {
                    "object_id": "chapter.current",
                    "layer": Layer.CORE_STATE_AUTHORITATIVE.value,
                    "domain": domain,
                    "domain_path": "chapter.current",
                },
                "field_patch": {"title": title},
            }
        ],
        "reason": "api governed block mutation",
    }


class _MockStoryLLMService:
    async def chat_completion(self, request):
        system_prompt = request.messages[0].content or ""
        user_payload = request.messages[1].content or ""

        if "longform_orchestrator" in system_prompt:
            payload = json.loads(user_payload)
            command_kind = payload["command_kind"]
            if command_kind == "generate_outline":
                content = {
                    "output_kind": "chapter_outline",
                    "needs_retrieval": False,
                    "archival_queries": [],
                    "recall_queries": [],
                    "specialist_focus": ["outline beats", "chapter intent"],
                    "writer_instruction": "Draft the opening chapter outline.",
                    "notes": ["mock_orchestrator"],
                }
            elif command_kind == "write_next_segment":
                content = {
                    "output_kind": "story_segment",
                    "needs_retrieval": False,
                    "archival_queries": [],
                    "recall_queries": [],
                    "specialist_focus": ["segment continuity", "tension"],
                    "writer_instruction": "Write the next story segment.",
                    "notes": ["mock_orchestrator"],
                }
            else:
                content = {
                    "output_kind": "discussion_message",
                    "needs_retrieval": False,
                    "archival_queries": [],
                    "recall_queries": [],
                    "specialist_focus": ["discussion"],
                    "writer_instruction": "Reply to the discussion prompt.",
                    "notes": ["mock_orchestrator"],
                }
            return {
                "choices": [
                    {"message": {"role": "assistant", "content": json.dumps(content)}}
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }

        if "longform_specialist" in system_prompt:
            payload = json.loads(user_payload)
            command_kind = payload["command_kind"]
            state_patch = {}
            recall_summary = None
            if command_kind == "accept_pending_segment":
                state_patch = {
                    "narrative_progress": {
                        "accepted_segments": 1,
                        "chapter_summary": "The courier secures the ledger and escapes the archive.",
                    }
                }
            elif command_kind == "complete_chapter":
                state_patch = {
                    "chapter_digest": {
                        "current_chapter": 1,
                        "last_accepted_excerpt": "The courier secures the ledger and escapes the archive.",
                    },
                    "narrative_progress": {
                        "accepted_segments": 1,
                        "chapter_summary": "The courier secures the ledger and escapes the archive.",
                    },
                }
                recall_summary = "Chapter 1: the courier steals the ledger and survives the archive pursuit."
            content = {
                "foundation_digest": ["Rivergate forbids open ritual fire."],
                "blueprint_digest": [
                    "Chapter one reveals the ledger and forces an escape."
                ],
                "current_outline_digest": [
                    "Open at the archive; end with a narrow escape."
                ],
                "recent_segment_digest": ["The courier slips into the archive vault."],
                "current_state_digest": ["chapter=1", "phase=segment_drafting"],
                "writer_hints": ["Keep tension immediate.", "Stay concrete and lean."],
                "validation_findings": [],
                "state_patch_proposals": state_patch,
                "summary_updates": ["mock specialist digest"],
                "recall_summary_text": recall_summary,
            }
            return {
                "choices": [
                    {"message": {"role": "assistant", "content": json.dumps(content)}}
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }

        content = "Writer fallback output."
        return {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def chat_completion_stream(self, request):
        user_prompt = request.messages[1].content or ""
        if "output_kind: chapter_outline" in user_prompt:
            text = "Chapter Outline: The courier infiltrates the archive, finds the ledger, and flees before sunrise."
        elif "output_kind: story_segment" in user_prompt:
            text = "The courier eased the ledger free, heard the ward-chimes flare, and ran before the archive doors sealed shut."
        else:
            text = "The outline should lean harder on the ledger's cost."
        yield f"data: {json.dumps({'type': 'text_delta', 'delta': text})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"


class _RecoverableStoryLLMService(_MockStoryLLMService):
    def __init__(self):
        super().__init__()
        self._stream_calls = 0

    async def chat_completion_stream(self, request):
        self._stream_calls += 1
        if self._stream_calls == 1:
            yield f"data: {json.dumps({'type': 'error', 'error': {'message': 'writer stream timeout', 'type': 'timeout'}})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        async for chunk in super().chat_completion_stream(request):
            yield chunk


class _FakeLangfuseObservation:
    def __init__(self, *, sink: list[dict], name: str) -> None:
        self._sink = sink
        self._name = name

    def __enter__(self):
        self._sink.append({"kind": "observation_enter", "name": self._name})
        return self

    def __exit__(self, exc_type, exc, tb):
        self._sink.append({"kind": "observation_exit", "name": self._name})
        return False

    def update(self, **kwargs):
        self._sink.append(
            {"kind": "observation_update", "name": self._name, "payload": kwargs}
        )

    def score_trace(self, **kwargs):
        self._sink.append(
            {"kind": "score_trace", "name": self._name, "payload": kwargs}
        )

    def score(self, **kwargs):
        self._sink.append({"kind": "score", "name": self._name, "payload": kwargs})

    def start_as_current_observation(self, **kwargs):
        return _FakeLangfuseObservation(
            sink=self._sink,
            name=str(kwargs.get("name") or "unknown"),
        )


class _FakeLangfuseContext:
    def __init__(self, *, sink: list[dict], payload: dict) -> None:
        self._sink = sink
        self._payload = payload

    def __enter__(self):
        self._sink.append({"kind": "propagate_enter", "payload": self._payload})
        return self

    def __exit__(self, exc_type, exc, tb):
        self._sink.append({"kind": "propagate_exit", "payload": self._payload})
        return False


class _FakeLangfuseService:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def propagate_attributes(self, **kwargs):
        return _FakeLangfuseContext(sink=self.events, payload=kwargs)

    def start_as_current_observation(self, **kwargs):
        return _FakeLangfuseObservation(
            sink=self.events,
            name=str(kwargs.get("name") or "unknown"),
        )


def _create_ready_workspace(client) -> str:
    workspace = client.post(
        "/api/rp/setup/workspaces",
        json={"story_id": "story_active_mvp", "mode": "longform"},
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["workspace_id"]

    assert (
        client.patch(
            f"/api/rp/setup/workspaces/{workspace_id}/story-config",
            json={
                "model_profile_ref": "model.default",
                "worker_profile_ref": "worker.longform",
                "post_write_policy_preset": "balanced",
                "retrieval_embedding_model_id": "embedding-model-story",
                "retrieval_embedding_provider_id": "provider-story",
                "retrieval_rerank_model_id": "rerank-model-story",
                "retrieval_rerank_provider_id": "provider-story",
                "notes": "Longform active story test",
            },
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/rp/setup/workspaces/{workspace_id}/writing-contract",
            json={
                "pov_rules": ["third_person_limited"],
                "style_rules": ["restrained", "lean"],
                "writing_constraints": ["avoid exposition dumps"],
                "task_writing_rules": ["keep scene motion visible"],
            },
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/rp/setup/workspaces/{workspace_id}/longform-blueprint",
            json={
                "premise": "A courier discovers the archive ledger is a prison key registry.",
                "central_conflict": "The courier must escape with proof before dawn.",
                "chapter_blueprints": [
                    {
                        "chapter_id": "ch1",
                        "title": "The Ledger",
                        "purpose": "Discover the registry and escape alive.",
                        "major_beats": ["Infiltration", "Discovery", "Escape"],
                        "setup_payoff_targets": ["prison key registry"],
                    }
                ],
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/rp/setup/workspaces/{workspace_id}/foundation/entries",
            json={
                "entry_id": "world_rule_fire",
                "domain": "world",
                "path": "law.fire_rituals",
                "title": "Fire Ritual Ban",
                "tags": ["law"],
                "source_refs": [],
                "content": {
                    "summary": "Rivergate forbids open ritual fire inside the archive district."
                },
            },
        ).status_code
        == 200
    )

    for step_id in (
        "story_config",
        "writing_contract",
        "foundation",
        "longform_blueprint",
    ):
        proposal = client.post(
            f"/api/rp/setup/workspaces/{workspace_id}/commit-proposals",
            json={
                "step_id": step_id,
                "target_draft_refs": [f"draft:{step_id}"],
                "reason": f"freeze {step_id}",
            },
        )
        assert proposal.status_code == 200
        proposal_id = proposal.json()["updated_refs"][0].split("proposal:", 1)[1]
        accepted = client.post(
            f"/api/rp/setup/workspaces/{workspace_id}/commit-proposals/{proposal_id}/accept"
        )
        assert accepted.status_code == 200

    activation_check = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activation-check"
    )
    assert activation_check.status_code == 200
    assert activation_check.json()["ready"] is True
    return workspace_id


def test_story_activation_bootstraps_session(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )

    activation = client.post(f"/api/rp/setup/workspaces/{workspace_id}/activate")
    assert activation.status_code == 200
    payload = activation.json()
    assert payload["current_phase"] == "outline_drafting"

    session_id = payload["session_id"]
    session_snapshot = client.get(f"/api/rp/story-sessions/{session_id}")
    assert session_snapshot.status_code == 200
    snapshot = session_snapshot.json()
    assert snapshot["session"]["story_id"] == "story_active_mvp"
    assert (
        snapshot["session"]["runtime_story_config"]["retrieval_embedding_model_id"]
        == "embedding-model-story"
    )
    assert (
        snapshot["session"]["runtime_story_config"]["retrieval_rerank_model_id"]
        == "rerank-model-story"
    )
    assert snapshot["chapter"]["chapter_index"] == 1
    assert snapshot["chapter"]["phase"] == "outline_drafting"
    assert snapshot["memory_backend"]["phase"] == "phase_g4c_cleanup_prep"
    assert snapshot["memory_backend"]["legacy_fields"] == {
        "session.current_state_json": "compatibility_mirror",
        "chapter.builder_snapshot_json": "compatibility_mirror",
    }
    assert snapshot["memory_backend"]["mirror_sync_enabled"] is True
    assert snapshot["memory_backend"]["hard_cleanup_enabled"] is False
    if snapshot["memory_backend"]["flags"]["core_state_store_write_switch_enabled"]:
        assert (
            snapshot["memory_backend"]["authoritative_truth_source"]
            == "core_state_store"
        )
        assert (
            snapshot["memory_backend"]["projection_truth_source"] == "core_state_store"
        )


def test_activation_check_emits_langfuse_scores(client, monkeypatch):
    fake_langfuse = _FakeLangfuseService()
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "api.rp_setup.get_langfuse_service",
        lambda: fake_langfuse,
    )

    activation_check = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activation-check",
        headers={"X-Request-Id": "req-activation-check-langfuse"},
    )

    assert activation_check.status_code == 200
    assert any(
        item["kind"] == "propagate_enter"
        and item["payload"]["session_id"] == workspace_id
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "activation.capability.readiness_gate"
        and item["payload"]["value"] == "pass"
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "activation.attribution.primary_suspects"
        for item in fake_langfuse.events
    )


def test_activation_bootstrap_emits_langfuse_scores(client, monkeypatch):
    fake_langfuse = _FakeLangfuseService()
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )
    monkeypatch.setattr(
        "api.rp_setup.get_langfuse_service",
        lambda: fake_langfuse,
    )

    activation = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate",
        headers={"X-Request-Id": "req-activation-langfuse"},
    )

    assert activation.status_code == 200
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "activation.capability.session_bootstrap.numeric"
        and item["payload"]["value"] == 1.0
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "activation.current_phase"
        and item["payload"]["value"] == "outline_drafting"
        for item in fake_langfuse.events
    )


def test_activation_failure_emits_langfuse_scores(client, monkeypatch):
    fake_langfuse = _FakeLangfuseService()
    workspace = client.post(
        "/api/rp/setup/workspaces",
        json={"story_id": "story_activation_not_ready", "mode": "longform"},
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["workspace_id"]
    monkeypatch.setattr(
        "api.rp_setup.get_langfuse_service",
        lambda: fake_langfuse,
    )

    activation = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate",
    )

    assert activation.status_code == 400
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "activation.attribution.setup_readiness_contract"
        and item["payload"]["value"] == "warn"
        for item in fake_langfuse.events
    )
    assert any(
        item["kind"] == "score_trace"
        and item["payload"]["name"] == "activation.attribution.primary_suspects"
        and "setup_readiness_contract" in item["payload"]["value"]
        for item in fake_langfuse.events
    )


def test_story_runtime_config_patch_updates_session_snapshot(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )

    session_id = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate"
    ).json()["session_id"]

    response = client.patch(
        f"/api/rp/story-sessions/{session_id}/runtime-config",
        json={
            "runtime_story_config": {
                "retrieval_embedding_provider_id": "provider-story",
                "retrieval_embedding_model_id": "embedding-model-session",
                "retrieval_rerank_provider_id": "provider-story",
                "retrieval_rerank_model_id": "rerank-model-session",
            }
        },
    )

    assert response.status_code == 200
    snapshot = response.json()
    assert (
        snapshot["session"]["runtime_story_config"]["retrieval_embedding_model_id"]
        == "embedding-model-session"
    )
    assert (
        snapshot["session"]["runtime_story_config"]["retrieval_rerank_model_id"]
        == "rerank-model-session"
    )

    refreshed = client.get(f"/api/rp/story-sessions/{session_id}")
    assert refreshed.status_code == 200
    refreshed_snapshot = refreshed.json()
    assert (
        refreshed_snapshot["session"]["runtime_story_config"][
            "retrieval_embedding_model_id"
        ]
        == "embedding-model-session"
    )
    assert (
        refreshed_snapshot["session"]["runtime_story_config"][
            "retrieval_rerank_model_id"
        ]
        == "rerank-model-session"
    )
    assert (
        refreshed_snapshot["memory_backend"]["legacy_fields"][
            "session.current_state_json"
        ]
        == "compatibility_mirror"
    )


def test_story_turn_chain_runs_outline_segment_and_complete(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )
    session_id = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate"
    ).json()["session_id"]

    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "generate_outline",
            "model_id": "model-story",
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "Chapter Outline" in body

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    outline_artifact = next(
        item
        for item in snapshot["artifacts"]
        if item["artifact_kind"] == "chapter_outline"
    )
    assert snapshot["chapter"]["phase"] == "outline_review"

    accepted_outline = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "accept_outline",
            "model_id": "model-story",
            "target_artifact_id": outline_artifact["artifact_id"],
        },
    )
    assert accepted_outline.status_code == 200
    assert accepted_outline.json()["current_phase"] == "segment_drafting"

    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "write_next_segment",
            "model_id": "model-story",
            "user_prompt": "Write the first escape segment.",
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "ward-chimes flare" in body

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    pending_segment = next(
        item
        for item in snapshot["artifacts"]
        if item["artifact_kind"] == "story_segment" and item["status"] == "draft"
    )
    assert snapshot["chapter"]["phase"] == "segment_review"

    accepted_segment = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "accept_pending_segment",
            "model_id": "model-story",
            "target_artifact_id": pending_segment["artifact_id"],
        },
    )
    assert accepted_segment.status_code == 200

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    assert snapshot["chapter"]["phase"] == "segment_drafting"
    assert (
        snapshot["session"]["current_state_json"]["narrative_progress"][
            "accepted_segments"
        ]
        >= 1
    )

    completed = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "complete_chapter",
            "model_id": "model-story",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["current_chapter_index"] == 2
    assert completed.json()["current_phase"] == "outline_drafting"

    chapter_two = client.get(f"/api/rp/story-sessions/{session_id}/chapters/2")
    assert chapter_two.status_code == 200
    assert chapter_two.json()["chapter"]["phase"] == "outline_drafting"


def test_story_runtime_debug_exposes_checkpoint_state(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )
    session_id = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate"
    ).json()["session_id"]

    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "generate_outline",
            "model_id": "model-story",
        },
    ) as stream_response:
        assert stream_response.status_code == 200
        _ = "".join(stream_response.iter_text())

    debug_response = client.get(f"/api/rp/story-sessions/{session_id}/runtime/debug")
    assert debug_response.status_code == 200
    payload = debug_response.json()
    assert payload["namespace"] == "rp_story"
    assert payload["latest_checkpoint"]["checkpoint_id"]
    assert payload["latest_meaningful_checkpoint"]["checkpoint_id"]
    assert payload["latest_meaningful_checkpoint"]["status"] in {
        "writer_completed",
        "completed",
        "artifact_persisted",
    }
    assert payload["latest_meaningful_checkpoint"]["state"]
    assert payload["history"]
    assert any(
        item["status"] in {"writer_completed", "completed", "artifact_persisted"}
        for item in payload["history"]
    )
    assert payload["history"]


def test_story_turn_rejects_command_not_allowed_for_phase(client):
    workspace_id = _create_ready_workspace(client)
    activation = client.post(f"/api/rp/setup/workspaces/{workspace_id}/activate")
    assert activation.status_code == 200
    session_id = activation.json()["session_id"]

    response = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "accept_outline",
            "model_id": "model-story",
        },
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"]["code"] == "story_turn_failed"
    assert (
        "not allowed during phase outline_drafting"
        in payload["detail"]["error"]["message"]
    )


def test_story_turn_recovers_after_failed_stream_on_same_thread(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _RecoverableStoryLLMService(),
    )
    session_id = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate"
    ).json()["session_id"]

    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "generate_outline",
            "model_id": "model-story",
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "writer stream timeout" in body

    retry = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "generate_outline",
            "model_id": "model-story",
        },
    )

    assert retry.status_code == 200
    payload = retry.json()
    assert payload["current_phase"] == "outline_review"
    assert payload["artifact_kind"] == "chapter_outline"
    assert payload["assistant_text"]


def test_story_memory_read_only_routes_expose_session_scoped_views(client, monkeypatch):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    workspace_id = _create_ready_workspace(client)
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )
    session_id = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate"
    ).json()["session_id"]

    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "generate_outline",
            "model_id": "model-story",
        },
    ) as response:
        assert response.status_code == 200
        _ = "".join(response.iter_text())

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    outline_artifact = next(
        item
        for item in snapshot["artifacts"]
        if item["artifact_kind"] == "chapter_outline"
    )
    accepted_outline = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "accept_outline",
            "model_id": "model-story",
            "target_artifact_id": outline_artifact["artifact_id"],
        },
    )
    assert accepted_outline.status_code == 200

    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "write_next_segment",
            "model_id": "model-story",
            "user_prompt": "Write the first escape segment.",
        },
    ) as response:
        assert response.status_code == 200
        _ = "".join(response.iter_text())

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    pending_segment = next(
        item
        for item in snapshot["artifacts"]
        if item["artifact_kind"] == "story_segment" and item["status"] == "draft"
    )
    accepted_segment = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "accept_pending_segment",
            "model_id": "model-story",
            "target_artifact_id": pending_segment["artifact_id"],
        },
    )
    assert accepted_segment.status_code == 200

    authoritative = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/authoritative"
    )
    projection = client.get(f"/api/rp/story-sessions/{session_id}/memory/projection")
    blocks = client.get(f"/api/rp/story-sessions/{session_id}/memory/blocks")
    proposals = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/proposals",
        params={"status": "applied"},
    )
    versions = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/versions",
        params={
            "object_id": "narrative_progress.current",
            "domain": "narrative_progress",
            "domain_path": "narrative_progress.current",
        },
    )
    provenance = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/provenance",
        params={
            "object_id": "narrative_progress.current",
            "domain": "narrative_progress",
            "domain_path": "narrative_progress.current",
        },
    )

    assert authoritative.status_code == 200
    assert projection.status_code == 200
    assert blocks.status_code == 200
    assert proposals.status_code == 200
    assert versions.status_code == 200
    assert provenance.status_code == 200
    assert any(
        item["object_ref"]["object_id"] == "narrative_progress.current"
        for item in authoritative.json()["items"]
    )
    assert any(
        item["slot_name"] == "current_outline_digest"
        for item in projection.json()["items"]
    )
    assert blocks.json()["session_id"] == session_id
    assert any(
        item["label"] == "narrative_progress.current"
        and item["layer"] == "core_state.authoritative"
        and item["domain"] == "narrative_progress"
        and item["domain_path"] == "narrative_progress.current"
        and isinstance(item["data_json"], dict)
        and item["source"] in {"core_state_store", "compatibility_mirror"}
        and item["metadata"]["route"]
        in {"core_state_store", "story_session.current_state_json"}
        for item in blocks.json()["items"]
    )
    assert any(
        item["label"] == "projection.current_outline_digest"
        and item["layer"] == "core_state.projection"
        and item["domain_path"] == "projection.current_outline_digest"
        and isinstance(item["items_json"], list)
        and item["source"] in {"core_state_store", "compatibility_mirror"}
        and item["metadata"]["route"]
        in {"core_state_store", "chapter_workspace.builder_snapshot_json"}
        for item in blocks.json()["items"]
    )
    assert proposals.json()["items"]
    assert versions.json()["current_ref"] == "narrative_progress.current@2"
    assert provenance.json()["proposal_refs"]


def test_story_memory_block_routes_read_formal_blocks_and_filter_list(
    client, monkeypatch
):
    monkeypatch.setenv(
        "CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED",
        "true",
    )
    get_settings.cache_clear()
    seeded = _seed_formal_memory_block_session()
    session_id = seeded["session_id"]

    blocks = client.get(f"/api/rp/story-sessions/{session_id}/memory/blocks")
    authoritative_only = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/blocks",
        params={"layer": Layer.CORE_STATE_AUTHORITATIVE.value},
    )
    runtime_workspace_only = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/blocks",
        params={"layer": Layer.RUNTIME_WORKSPACE.value},
    )
    core_store_only = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/blocks",
        params={"source": "core_state_store"},
    )
    runtime_workspace_source_only = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/blocks",
        params={"source": "runtime_workspace_store"},
    )
    authoritative_block = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['authoritative_block_id']}"
    )
    authoritative_versions = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['authoritative_block_id']}/versions"
    )
    authoritative_provenance = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['authoritative_block_id']}/provenance"
    )
    authoritative_proposals = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['authoritative_block_id']}/proposals"
    )
    authoritative_applied_proposals = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['authoritative_block_id']}/proposals",
        params={"status": "applied"},
    )
    block_consumers = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/block-consumers"
    )
    writer_packet_consumer = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/block-consumers/story.writer_packet"
    )
    projection_block = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['projection_block_id']}"
    )
    runtime_artifact_block = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['runtime_artifact_block_id']}"
    )
    runtime_discussion_block = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['runtime_discussion_block_id']}"
    )
    projection_proposals = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['projection_block_id']}/proposals"
    )
    runtime_artifact_proposals = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['runtime_artifact_block_id']}/proposals"
    )
    runtime_artifact_versions = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['runtime_artifact_block_id']}/versions"
    )
    runtime_discussion_provenance = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['runtime_discussion_block_id']}/provenance"
    )
    projection_versions = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['projection_block_id']}/versions"
    )
    projection_provenance = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['projection_block_id']}/provenance"
    )
    missing_block = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/blocks/missing-block"
    )
    missing_block_proposals = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/blocks/missing-block/proposals"
    )
    missing_consumer = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/block-consumers/missing-consumer"
    )
    missing_block_versions = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/blocks/missing-block/versions"
    )
    missing_block_provenance = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/blocks/missing-block/provenance"
    )
    missing_session = client.get(
        "/api/rp/story-sessions/missing-session/memory/blocks/missing-block"
    )
    missing_session_proposals = client.get(
        "/api/rp/story-sessions/missing-session/memory/blocks/missing-block/proposals"
    )
    missing_session_consumers = client.get(
        "/api/rp/story-sessions/missing-session/memory/block-consumers"
    )
    missing_session_versions = client.get(
        "/api/rp/story-sessions/missing-session/memory/blocks/missing-block/versions"
    )

    assert blocks.status_code == 200
    assert authoritative_only.status_code == 200
    assert runtime_workspace_only.status_code == 200
    assert core_store_only.status_code == 200
    assert runtime_workspace_source_only.status_code == 200
    assert authoritative_block.status_code == 200
    assert authoritative_versions.status_code == 200
    assert authoritative_provenance.status_code == 200
    assert authoritative_proposals.status_code == 200
    assert authoritative_applied_proposals.status_code == 200
    assert block_consumers.status_code == 200
    assert writer_packet_consumer.status_code == 200
    assert projection_block.status_code == 200
    assert runtime_artifact_block.status_code == 200
    assert runtime_discussion_block.status_code == 200
    assert projection_proposals.status_code == 200
    assert runtime_artifact_proposals.status_code == 200
    assert projection_versions.status_code == 200
    assert projection_provenance.status_code == 200
    assert runtime_artifact_versions.status_code == 400
    assert runtime_discussion_provenance.status_code == 400
    assert blocks.json()["session_id"] == session_id
    assert all(
        item["layer"] == Layer.CORE_STATE_AUTHORITATIVE.value
        for item in authoritative_only.json()["items"]
    )
    assert all(
        item["layer"] == Layer.RUNTIME_WORKSPACE.value
        for item in runtime_workspace_only.json()["items"]
    )
    assert all(
        item["source"] == "core_state_store" for item in core_store_only.json()["items"]
    )
    assert all(
        item["source"] == "runtime_workspace_store"
        for item in runtime_workspace_source_only.json()["items"]
    )
    assert all(
        seeded["accepted_runtime_artifact_id"] not in item["block_id"]
        for item in runtime_workspace_only.json()["items"]
    )

    authoritative_item = authoritative_block.json()["item"]
    projection_item = projection_block.json()["item"]
    runtime_artifact_item = runtime_artifact_block.json()["item"]
    runtime_discussion_item = runtime_discussion_block.json()["item"]
    assert authoritative_block.json()["session_id"] == session_id
    assert authoritative_item["block_id"] == seeded["authoritative_block_id"]
    assert authoritative_item["label"] == "chapter.current"
    assert authoritative_item["layer"] == Layer.CORE_STATE_AUTHORITATIVE.value
    assert authoritative_item["source"] == "core_state_store"
    assert authoritative_item["data_json"] == {
        "current_chapter": 1,
        "title": "Formal API Chapter",
    }
    assert authoritative_item["metadata"]["source_table"] == (
        "rp_core_state_authoritative_objects"
    )
    assert projection_item["block_id"] == seeded["projection_block_id"]
    assert projection_item["label"] == "projection.current_outline_digest"
    assert projection_item["layer"] == Layer.CORE_STATE_PROJECTION.value
    assert projection_item["source"] == "core_state_store"
    assert projection_item["items_json"] == ["Formal API outline"]
    assert projection_item["metadata"]["source_table"] == (
        "rp_core_state_projection_slots"
    )
    assert runtime_artifact_item["block_id"] == seeded["runtime_artifact_block_id"]
    assert runtime_artifact_item["label"].startswith("runtime_workspace.artifact.")
    assert runtime_artifact_item["layer"] == Layer.RUNTIME_WORKSPACE.value
    assert runtime_artifact_item["source"] == "runtime_workspace_store"
    assert runtime_artifact_item["data_json"]["artifact_kind"] == (
        StoryArtifactKind.STORY_SEGMENT.value
    )
    assert runtime_artifact_item["data_json"]["status"] == (
        StoryArtifactStatus.DRAFT.value
    )
    assert runtime_artifact_item["metadata"]["source_table"] == "rp_story_artifacts"
    assert runtime_discussion_item["block_id"] == seeded["runtime_discussion_block_id"]
    assert runtime_discussion_item["label"].startswith("runtime_workspace.discussion.")
    assert runtime_discussion_item["layer"] == Layer.RUNTIME_WORKSPACE.value
    assert runtime_discussion_item["source"] == "runtime_workspace_store"
    assert runtime_discussion_item["data_json"]["role"] == "assistant"
    assert runtime_discussion_item["metadata"]["source_table"] == (
        "rp_story_discussion_entries"
    )
    assert authoritative_versions.json() == {
        "session_id": session_id,
        "block_id": seeded["authoritative_block_id"],
        "versions": ["chapter.current@5"],
        "current_ref": "chapter.current@5",
    }
    assert authoritative_provenance.json()["session_id"] == session_id
    assert (
        authoritative_provenance.json()["block_id"]
        == (seeded["authoritative_block_id"])
    )
    assert authoritative_provenance.json()["target_ref"] == {
        "object_id": "chapter.current",
        "layer": Layer.CORE_STATE_AUTHORITATIVE.value,
        "domain": Domain.CHAPTER.value,
        "domain_path": "chapter.current",
        "scope": "story",
        "revision": 5,
    }
    assert authoritative_provenance.json()["source_refs"] == [
        "core_state_store:authoritative_revision"
    ]
    authoritative_proposal_payload = authoritative_proposals.json()
    authoritative_proposal_ids = {
        item["proposal_id"] for item in authoritative_proposal_payload["items"]
    }
    assert authoritative_proposal_payload["session_id"] == session_id
    assert (
        authoritative_proposal_payload["block_id"] == seeded["authoritative_block_id"]
    )
    assert authoritative_proposal_ids == {
        seeded["matching_review_required_proposal_id"],
        seeded["matching_applied_proposal_id"],
    }
    assert seeded["same_domain_other_proposal_id"] not in authoritative_proposal_ids
    authoritative_applied_items = authoritative_applied_proposals.json()["items"]
    assert len(authoritative_applied_items) == 1
    assert (
        authoritative_applied_items[0]["proposal_id"]
        == (seeded["matching_applied_proposal_id"])
    )
    assert authoritative_applied_items[0]["status"] == "applied"
    consumer_items = block_consumers.json()["items"]
    assert block_consumers.json()["session_id"] == session_id
    assert {item["consumer_key"] for item in consumer_items} == {
        "story.orchestrator",
        "story.specialist",
        "story.writer_packet",
    }
    assert all(item["dirty"] is True for item in consumer_items)
    writer_packet_payload = writer_packet_consumer.json()["item"]
    assert writer_packet_payload["consumer_key"] == "story.writer_packet"
    assert all(
        item["layer"] == Layer.CORE_STATE_PROJECTION.value
        for item in writer_packet_payload["attached_blocks"]
    )
    assert "projection.current_outline_digest" in {
        item["label"] for item in writer_packet_payload["attached_blocks"]
    }
    assert projection_versions.json() == {
        "session_id": session_id,
        "block_id": seeded["projection_block_id"],
        "versions": ["projection.current_outline_digest@6"],
        "current_ref": "projection.current_outline_digest@6",
    }
    assert projection_provenance.json()["session_id"] == session_id
    assert projection_provenance.json()["block_id"] == seeded["projection_block_id"]
    assert projection_provenance.json()["target_ref"] == {
        "object_id": "projection.current_outline_digest",
        "layer": Layer.CORE_STATE_PROJECTION.value,
        "domain": Domain.CHAPTER.value,
        "domain_path": "projection.current_outline_digest",
        "scope": "chapter",
        "revision": 6,
    }
    assert projection_provenance.json()["source_refs"] == [
        "core_state_store:projection_slot_revision"
    ]
    assert projection_proposals.json() == {
        "session_id": session_id,
        "block_id": seeded["projection_block_id"],
        "items": [],
    }
    assert runtime_artifact_proposals.json() == {
        "session_id": session_id,
        "block_id": seeded["runtime_artifact_block_id"],
        "items": [],
    }
    assert (
        runtime_artifact_versions.json()["detail"]["error"]["code"]
        == "memory_block_history_unsupported"
    )
    assert (
        runtime_discussion_provenance.json()["detail"]["error"]["code"]
        == "memory_block_history_unsupported"
    )

    assert missing_block.status_code == 404
    assert missing_block.json()["detail"]["error"]["code"] == "memory_block_not_found"
    assert missing_block_proposals.status_code == 404
    assert (
        missing_block_proposals.json()["detail"]["error"]["code"]
        == "memory_block_not_found"
    )
    assert missing_consumer.status_code == 404
    assert (
        missing_consumer.json()["detail"]["error"]["code"]
        == "memory_block_consumer_not_found"
    )
    assert missing_block_versions.status_code == 404
    assert (
        missing_block_versions.json()["detail"]["error"]["code"]
        == "memory_block_not_found"
    )
    assert missing_block_provenance.status_code == 404
    assert (
        missing_block_provenance.json()["detail"]["error"]["code"]
        == "memory_block_not_found"
    )
    assert missing_session.status_code == 404
    assert (
        missing_session.json()["detail"]["error"]["code"] == "story_session_not_found"
    )
    assert missing_session_proposals.status_code == 404
    assert (
        missing_session_proposals.json()["detail"]["error"]["code"]
        == "story_session_not_found"
    )
    assert missing_session_consumers.status_code == 404
    assert (
        missing_session_consumers.json()["detail"]["error"]["code"]
        == "story_session_not_found"
    )
    assert missing_session_versions.status_code == 404
    assert (
        missing_session_versions.json()["detail"]["error"]["code"]
        == "story_session_not_found"
    )


def test_story_memory_block_proposal_submission_is_governed(client, monkeypatch):
    monkeypatch.setenv(
        "CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED",
        "true",
    )
    get_settings.cache_clear()
    seeded = _seed_formal_memory_block_session()
    session_id = seeded["session_id"]
    authoritative_route = (
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['authoritative_block_id']}/proposals"
    )
    projection_route = (
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['projection_block_id']}/proposals"
    )

    success = client.post(
        authoritative_route,
        json=_authoritative_block_patch_payload(title="Governed API Chapter"),
    )
    mismatch = client.post(
        authoritative_route,
        json=_authoritative_block_patch_payload(
            title="Wrong Domain API Chapter",
            domain=Domain.TIMELINE.value,
        ),
    )
    projection = client.post(
        projection_route,
        json={
            "operations": [
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "projection.current_outline_digest",
                        "layer": Layer.CORE_STATE_PROJECTION.value,
                        "domain": Domain.CHAPTER.value,
                        "domain_path": "projection.current_outline_digest",
                    },
                    "field_patch": {"items": ["Projection proposal"]},
                }
            ],
            "reason": "projection mutation should fail",
        },
    )
    missing_block = client.post(
        f"/api/rp/story-sessions/{session_id}/memory/blocks/missing-block/proposals",
        json=_authoritative_block_patch_payload(title="Missing Block"),
    )
    missing_session = client.post(
        "/api/rp/story-sessions/missing-session/"
        f"memory/blocks/{seeded['authoritative_block_id']}/proposals",
        json=_authoritative_block_patch_payload(title="Missing Session"),
    )
    proposals = client.get(authoritative_route)
    review_required_proposals = client.get(
        authoritative_route,
        params={"status": "review_required"},
    )

    assert success.status_code == 200
    success_payload = success.json()
    success_item = success_payload["item"]
    assert success_payload["session_id"] == session_id
    assert success_payload["block_id"] == seeded["authoritative_block_id"]
    assert success_item["status"] == "review_required"
    assert success_item["domain"] == Domain.CHAPTER.value
    assert success_item["domain_path"] == "chapter.current"
    assert success_item["operation_kinds"] == ["patch_fields"]

    proposal_ids = {item["proposal_id"] for item in proposals.json()["items"]}
    review_required_ids = {
        item["proposal_id"] for item in review_required_proposals.json()["items"]
    }
    assert success_item["proposal_id"] in proposal_ids
    assert success_item["proposal_id"] in review_required_ids

    assert mismatch.status_code == 400
    assert mismatch.json()["detail"]["error"]["code"] == "memory_block_target_mismatch"
    assert projection.status_code == 400
    assert (
        projection.json()["detail"]["error"]["code"]
        == "memory_block_mutation_unsupported"
    )
    assert missing_block.status_code == 404
    assert missing_block.json()["detail"]["error"]["code"] == "memory_block_not_found"
    assert missing_session.status_code == 404
    assert (
        missing_session.json()["detail"]["error"]["code"] == "story_session_not_found"
    )


def test_story_memory_block_proposal_detail_and_apply_routes(client, monkeypatch):
    monkeypatch.setenv(
        "CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED",
        "true",
    )
    get_settings.cache_clear()
    seeded = _seed_formal_memory_block_session()
    session_id = seeded["session_id"]
    proposal_id = seeded["matching_review_required_proposal_id"]
    detail_route = (
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['authoritative_block_id']}/proposals/{proposal_id}"
    )
    apply_route = detail_route + "/apply"
    applied_detail_route = (
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['authoritative_block_id']}/proposals/"
        f"{seeded['matching_applied_proposal_id']}"
    )
    list_route = (
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{seeded['authoritative_block_id']}/proposals"
    )

    detail = client.get(detail_route)
    applied_detail = client.get(applied_detail_route)
    apply = client.post(apply_route)
    replay = client.post(apply_route)
    applied_list = client.get(list_route, params={"status": "applied"})

    assert detail.status_code == 200
    detail_item = detail.json()["item"]
    assert detail.json()["proposal_id"] == proposal_id
    assert detail_item["status"] == "review_required"
    assert detail_item["reason"] == "api review required detail"
    assert detail_item["trace_id"] == "trace-api-review-required"
    assert detail_item["error_message"] is None
    assert detail_item["operations"][0]["field_patch"] == {
        "title": "Pending API Chapter"
    }
    assert detail_item["base_refs"][0]["revision"] == 5
    assert detail_item["apply_receipts"] == []

    assert applied_detail.status_code == 200
    applied_detail_item = applied_detail.json()["item"]
    assert applied_detail_item["status"] == "applied"
    assert len(applied_detail_item["apply_receipts"]) == 1
    assert applied_detail_item["apply_receipts"][0]["apply_backend"] == "adapter_backed"

    assert apply.status_code == 200
    applied_item = apply.json()["item"]
    assert applied_item["status"] == "applied"
    assert applied_item["applied_at"] is not None
    assert len(applied_item["apply_receipts"]) == 1
    assert applied_item["apply_receipts"][0]["target_refs"][0]["object_id"] == (
        "chapter.current"
    )

    assert replay.status_code == 200
    assert replay.json()["item"] == applied_item

    applied_ids = {item["proposal_id"] for item in applied_list.json()["items"]}
    assert proposal_id in applied_ids
    assert seeded["matching_applied_proposal_id"] in applied_ids


def test_story_memory_block_proposal_detail_and_apply_errors(client, monkeypatch):
    monkeypatch.setenv(
        "CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED",
        "true",
    )
    get_settings.cache_clear()
    seeded = _seed_formal_memory_block_session()
    session_id = seeded["session_id"]
    block_id = seeded["authoritative_block_id"]
    projection_block_id = seeded["projection_block_id"]
    runtime_artifact_block_id = seeded["runtime_artifact_block_id"]

    wrong_block_detail = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{block_id}/proposals/"
        f"{seeded['same_domain_other_proposal_id']}"
    )
    projection_detail = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{projection_block_id}/proposals/missing-proposal"
    )
    runtime_detail = client.get(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{runtime_artifact_block_id}/proposals/missing-proposal"
    )
    projection_apply = client.post(
        "/api/rp/story-sessions/"
        f"{session_id}/memory/blocks/{projection_block_id}/proposals/"
        f"{seeded['projection_target_proposal_id']}/apply"
    )
    missing_block_detail = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/blocks/missing-block/proposals/missing-proposal"
    )
    missing_session_apply = client.post(
        "/api/rp/story-sessions/missing-session/"
        f"memory/blocks/{block_id}/proposals/{seeded['matching_review_required_proposal_id']}/apply"
    )

    assert wrong_block_detail.status_code == 404
    assert (
        wrong_block_detail.json()["detail"]["error"]["code"]
        == "memory_block_proposal_not_found"
    )
    assert projection_detail.status_code == 400
    assert (
        projection_detail.json()["detail"]["error"]["code"]
        == "memory_block_mutation_unsupported"
    )
    assert runtime_detail.status_code == 400
    assert (
        runtime_detail.json()["detail"]["error"]["code"]
        == "memory_block_mutation_unsupported"
    )
    assert projection_apply.status_code == 400
    assert (
        projection_apply.json()["detail"]["error"]["code"]
        == "memory_block_mutation_unsupported"
    )
    assert missing_block_detail.status_code == 404
    assert (
        missing_block_detail.json()["detail"]["error"]["code"]
        == "memory_block_not_found"
    )
    assert missing_session_apply.status_code == 404
    assert (
        missing_session_apply.json()["detail"]["error"]["code"]
        == "story_session_not_found"
    )


def test_story_memory_routes_return_404_for_missing_session(client):
    routes = [
        ("/api/rp/story-sessions/missing-session/memory/authoritative", None),
        ("/api/rp/story-sessions/missing-session/memory/projection", None),
        ("/api/rp/story-sessions/missing-session/memory/blocks", None),
        ("/api/rp/story-sessions/missing-session/memory/block-consumers", None),
        ("/api/rp/story-sessions/missing-session/memory/blocks/missing-block", None),
        (
            "/api/rp/story-sessions/missing-session/memory/blocks/missing-block/proposals",
            None,
        ),
        (
            "/api/rp/story-sessions/missing-session/memory/blocks/missing-block/versions",
            None,
        ),
        (
            "/api/rp/story-sessions/missing-session/memory/blocks/missing-block/provenance",
            None,
        ),
        ("/api/rp/story-sessions/missing-session/memory/proposals", None),
        (
            "/api/rp/story-sessions/missing-session/memory/versions",
            {
                "object_id": "chapter.current",
                "domain": "chapter",
                "domain_path": "chapter.current",
            },
        ),
        (
            "/api/rp/story-sessions/missing-session/memory/provenance",
            {
                "object_id": "chapter.current",
                "domain": "chapter",
                "domain_path": "chapter.current",
            },
        ),
    ]

    for route, params in routes:
        response = client.get(route, params=params)
        assert response.status_code == 404
        payload = response.json()
        assert payload["detail"]["error"]["code"] == "story_session_not_found"


def test_story_memory_routes_do_not_fall_back_to_story_latest_session(
    client, monkeypatch
):
    client.put("/api/providers/provider-story", json=_provider_payload())
    client.put(
        "/api/providers/provider-story/models/model-story",
        json=_model_payload(),
    )
    monkeypatch.setattr(
        "rp.services.story_llm_gateway.get_litellm_service",
        lambda: _MockStoryLLMService(),
    )

    workspace_id = _create_ready_workspace(client)
    session_id = client.post(
        f"/api/rp/setup/workspaces/{workspace_id}/activate"
    ).json()["session_id"]

    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "generate_outline",
            "model_id": "model-story",
        },
    ) as response:
        assert response.status_code == 200
        _ = "".join(response.iter_text())

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    outline_artifact = next(
        item
        for item in snapshot["artifacts"]
        if item["artifact_kind"] == "chapter_outline"
    )
    accepted_outline = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "accept_outline",
            "model_id": "model-story",
            "target_artifact_id": outline_artifact["artifact_id"],
        },
    )
    assert accepted_outline.status_code == 200

    with client.stream(
        "POST",
        f"/api/rp/story-sessions/{session_id}/turn/stream",
        json={
            "session_id": session_id,
            "command_kind": "write_next_segment",
            "model_id": "model-story",
            "user_prompt": "Write the first escape segment.",
        },
    ) as response:
        assert response.status_code == 200
        _ = "".join(response.iter_text())

    snapshot = client.get(f"/api/rp/story-sessions/{session_id}").json()
    pending_segment = next(
        item
        for item in snapshot["artifacts"]
        if item["artifact_kind"] == "story_segment" and item["status"] == "draft"
    )
    accepted_segment = client.post(
        f"/api/rp/story-sessions/{session_id}/turn",
        json={
            "session_id": session_id,
            "command_kind": "accept_pending_segment",
            "model_id": "model-story",
            "target_artifact_id": pending_segment["artifact_id"],
        },
    )
    assert accepted_segment.status_code == 200

    with SqlSession(get_engine()) as db_session:
        story_session_service = StorySessionService(db_session)
        newer_session = story_session_service.create_session(
            story_id="story_active_mvp",
            source_workspace_id="workspace-memory-latest",
            mode="longform",
            runtime_story_config={},
            writer_contract={},
            current_state_json={
                "chapter_digest": {"current_chapter": 1, "title": "Fresh Session"},
                "narrative_progress": {
                    "current_phase": LongformChapterPhase.OUTLINE_DRAFTING.value,
                    "accepted_segments": 0,
                },
                "timeline_spine": [],
                "active_threads": [],
                "foreshadow_registry": [],
                "character_state_digest": {},
            },
            initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
        )
        story_session_service.create_chapter_workspace(
            session_id=newer_session.session_id,
            chapter_index=1,
            phase=LongformChapterPhase.OUTLINE_DRAFTING,
            builder_snapshot_json={
                "foundation_digest": ["Found B"],
                "blueprint_digest": ["Blueprint B"],
                "current_outline_digest": ["Outline B"],
                "recent_segment_digest": ["Segment B"],
                "current_state_digest": ["State B"],
            },
        )
        story_session_service.commit()

    versions = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/versions",
        params={
            "object_id": "narrative_progress.current",
            "domain": "narrative_progress",
            "domain_path": "narrative_progress.current",
        },
    )
    provenance = client.get(
        f"/api/rp/story-sessions/{session_id}/memory/provenance",
        params={
            "object_id": "narrative_progress.current",
            "domain": "narrative_progress",
            "domain_path": "narrative_progress.current",
        },
    )

    assert versions.status_code == 200
    assert provenance.status_code == 200
    assert versions.json()["current_ref"] == "narrative_progress.current@2"
    assert provenance.json()["proposal_refs"]
