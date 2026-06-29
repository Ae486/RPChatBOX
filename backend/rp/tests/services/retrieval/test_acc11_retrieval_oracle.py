"""S-Y2 oracle: ACC-11-retrieval-1..12 capstone.

Deterministic L1 acceptance surface that binds the already-landed retrieval
contracts into one coherent oracle. Each ACC is either asserted here through a
real production path or explicitly deferred with a reason when ownership sits
outside the retrieval slice.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from models.rp_story_store import StoryTurnRecord
from rp.models.memory.contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.retrieval.runtime_contracts import (
    RetrievalUsageLedgerSnapshot,
    RuntimeRetrievalSearchInput,
)
from rp.models.runtime.workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.shared.dsl import Domain
from rp.models.story.runtime import (
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
)
from rp.models.writer.worker_family import WorkerFamily
from rp.services.retrieval.retrieval_failure_classifier import (
    classify_writer_retrieval_outcome,
)
from rp.services.retrieval.retrieval_tool_definitions import (
    WRITER_RETRIEVAL_EXPAND_TOOL,
    WRITER_RETRIEVAL_SEARCH_TOOL,
    WRITER_RETRIEVAL_USAGE_TOOL,
)
from rp.services.retrieval.runtime_retrieval_tool_provider import (
    RuntimeRetrievalToolProvider,
)
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.turn_domain_service import WriterFinalizationRejected
from rp.services.writer.worker_executor_dispatcher import (
    WorkerExecutorDispatcher,
    WorkerExecutorRoute,
)
from rp.services.writer.worker_registry_service import (
    LONGFORM_MEMORY_WORKER_ID,
    WorkerRegistryService,
)
from rp.services.writer.writing_worker_execution_service import (
    WritingWorkerExecutionService,
)
from rp.services.writer.writer_retrieval_errors import WriterRetrievalError
from rp.tests.services.projection.test_projection_builder_services import (
    _build_turn_domain_service,
    _seed_story_runtime as _seed_projection_story_runtime,
)
from rp.tests.services.retrieval.test_retrieval_failure_classifier import (
    _outcome,
    _real_tool_not_allowed,
    _real_zero_hit_search,
)
from rp.tests.services.retrieval.test_runtime_retrieval_tool_provider import (
    _AllowUsageGuard,
    _FakeRetrievalSearchService,
    _FakeRuntimeRetrievalCardService,
    _FakeSearchExecution,
    _call,
    _identity,
)
from rp.tests.services.story.test_runtime_debug_retrieval_observability_split import (
    _CARD_EXCERPT,
    _CARD_SHORT_ID,
    _CARD_SUMMARY,
    _CARD_TITLE,
    _QUERY_TEXT,
    _build as _build_debug_query,
    _card_material,
    _miss_material,
    _turn_trace,
    _usage_material,
)
from rp.tests.services.story.test_session_pointer_write_authority import (
    _seed_settled_main_turns,
)
from rp.tests.services.story.test_sy1_durable_finalization_gate import (
    USAGE_REQUIRED_CODE,
    _gate_identity,
    _persist,
    _prepare_segment_turn,
    _seed_material,
)
from rp.tests.services.story.test_s3_7_pre_s4_readiness import (
    _ToolLoopGateway as _HarnessToolGateway,
)
from rp.tests.services.writer.test_worker_executor_dispatcher import (
    _FailIfCalledAdapter,
    _registration,
    _request,
    _service,
)
from rp.tests.services.writer.test_worker_family_and_tool_policy import (
    _seed_and_publish_longform_snapshot,
)
from rp.tests.services.writer.test_writing_worker_retrieval_loop_service import (
    _OneShotGateway,
    _build_identity,
    _build_packet,
)


_LLM_AGENT_FAMILIES = {"writer", "orchestrator", "worker", "brainstorm"}


def _record_packet_visible_retrieval_materials(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
) -> RuntimeWorkspaceMaterialService:
    workspace = RuntimeWorkspaceMaterialService(session=retrieval_session)
    workspace.record_material(
        RuntimeWorkspaceMaterial(
            material_id="packet-card-R1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=identity,
            domain="chapter",
            domain_path="chapter.runtime.packet.card",
            short_id="R1",
            payload={
                "hit_id": "raw-hit-1",
                "summary": "A recalled storm callback matters here.",
                "title": "Storm Callback",
            },
            visibility=RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
            created_by="worker.specialist",
        )
    )
    workspace.record_material(
        RuntimeWorkspaceMaterial(
            material_id="packet-expanded-X1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK,
            identity=identity,
            domain="chapter",
            domain_path="chapter.runtime.packet.expanded",
            short_id="X1",
            payload={
                "chunk_id": "raw-chunk-1",
                "summary": "Expanded detail: the seal broke during the first storm.",
                "text": "Expanded detail: the seal broke during the first storm.",
                "title": "Storm Callback Expanded",
            },
            lifecycle=RuntimeWorkspaceMaterialLifecycle.EXPANDED,
            visibility=RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
            created_by="worker.specialist",
        )
    )
    return workspace


def _record_retrieval_card(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    material_id: str,
    short_id: str,
    marker: str,
    ttl: str,
    version: str,
) -> RuntimeWorkspaceMaterialService:
    workspace = RuntimeWorkspaceMaterialService(session=retrieval_session)
    workspace.record_material(
        RuntimeWorkspaceMaterial(
            material_id=material_id,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=identity,
            domain=Domain.CHAPTER.value,
            domain_path=f"chapter.runtime.retrieval.{marker}",
            short_id=short_id,
            payload={
                "query_text": marker,
                "summary": f"{marker} summary",
                "text": f"{marker} text",
                "title": f"{marker} title",
            },
            visibility=RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
            created_by="test.acc11.rollback",
            source_refs=[
                MemorySourceRef(
                    source_type="retrieval_hit",
                    source_id=f"hit:{marker}",
                    layer="recall",
                    domain=Domain.CHAPTER.value,
                    block_id=f"chapter.runtime.retrieval.{marker}",
                    metadata={"source_of_truth": False},
                )
            ],
            metadata={
                "ttl": ttl,
                "version": version,
                "retrieval_layer": "recall",
                "source_of_truth": False,
            },
        )
    )
    return workspace


def _seed_runtime_identity_for_packet(retrieval_session) -> tuple[
    object,
    MemoryRuntimeIdentity,
    RuntimeWorkspaceMaterialService,
]:
    session, _, story_service = _seed_projection_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.acc11.packet",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    workspace = _record_packet_visible_retrieval_materials(
        retrieval_session,
        identity=identity,
    )
    return story_service, identity, workspace


def _build_packet_with_runtime_retrieval_context(retrieval_session):
    story_service, identity, workspace = _seed_runtime_identity_for_packet(
        retrieval_session
    )
    turn_domain_service = _build_turn_domain_service(
        story_service,
        runtime_identity_service=StoryRuntimeIdentityService(
            retrieval_session,
            runtime_profile_snapshot_service=RuntimeProfileSnapshotService(
                retrieval_session
            ),
        ),
        runtime_workspace_material_service=workspace,
    )
    bundle = SpecialistResultBundle(
        foundation_digest=["Found A"],
        blueprint_digest=["Blueprint A"],
        current_outline_digest=["Outline A"],
        recent_segment_digest=["Segment A"],
        current_state_digest=["State A"],
        writer_hints=["Hint A"],
    )
    plan = OrchestratorPlan(
        output_kind=StoryArtifactKind.STORY_SEGMENT,
        writer_instruction="Write the next segment.",
    )
    packet = turn_domain_service.build_packet(
        session_id=identity.session_id,
        plan=plan,
        specialist_bundle=bundle,
        runtime_identity=identity,
    )
    return packet, identity, workspace


def test_acc11_retrieval_1_design_taxonomy_excludes_retrieval_and_runtime_registry_has_no_retrieval_worker(
    retrieval_session,
) -> None:
    """ACC-11-retrieval-1: "Retrieval has no entry in the LLM agent-family taxonomy and is reachable only via allowlisted tools."

    Owning slice: S-Y2 capstone. Evidence: spec-freeze lines 137-139; grill notes
    lines 500-508; final grill queue lines 33-39, 440-441, 583-585; module doc
    lines 9-10, 26, 30-32.
    """

    snapshot = _seed_and_publish_longform_snapshot(retrieval_session)
    registry = WorkerRegistryService(retrieval_session).build_registry_for_snapshot(
        snapshot_id=snapshot.runtime_profile_snapshot_id
    )

    # Design-taxonomy premise from the frozen docs: retrieval is a capability,
    # not a node-1 LLM agent family. Give that proposition teeth by combining it
    # with the live runtime registry: if a retrieval agent family ever becomes a
    # registered runtime worker family, this ACC must fail.
    assert _LLM_AGENT_FAMILIES == {"writer", "orchestrator", "worker", "brainstorm"}
    assert "retrieval" not in _LLM_AGENT_FAMILIES
    assert not any(
        worker.descriptor.family == WorkerFamily.RETRIEVAL
        for worker in registry.workers
    )


@pytest.mark.asyncio
async def test_acc11_retrieval_1_worker_family_retrieval_has_no_dedicated_agent_executor_route():
    """ACC-11-retrieval-1: "Retrieval has no entry in the LLM agent-family taxonomy and is reachable only via allowlisted tools."

    Owning slice: S-Y2 capstone. Evidence: `WorkerFamily` is a dispatcher
    routing key only, while `WorkerExecutorRoute` has no retrieval-specific
    executor and `WorkerExecutionService` degrades a retrieval family request.
    """

    dispatcher = WorkerExecutorDispatcher()
    service = _service(longform_memory_worker_adapter=_FailIfCalledAdapter())
    request = _request(worker_id="RetrievalWorker")
    registration = _registration(
        worker_id="RetrievalWorker",
        family=WorkerFamily.RETRIEVAL,
        allow_degrade=True,
    )

    outcome = await service._execute_one(  # noqa: SLF001
        request=request,
        registration=registration,
        session=object(),
        chapter=object(),
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model-a",
        provider_id="provider-a",
        user_prompt="Continue.",
        orchestrator_plan=object(),
        accepted_segments=[],
        pending_artifact=None,
    )

    assert {route.value for route in WorkerExecutorRoute} == {
        "memory_maintenance_structured_output",
        "writer_tool_loop_harness",
        "unsupported",
    }
    assert dispatcher.resolve(WorkerFamily.RETRIEVAL) == (
        WorkerExecutorRoute.WRITER_TOOL_LOOP_HARNESS
    )
    assert outcome.worker_result.metadata["degrade_reason"] == (
        "runtime_worker_executor_missing"
    )


@pytest.mark.asyncio
async def test_acc11_retrieval_1_retrieval_is_reachable_only_through_allowlisted_tools():
    """ACC-11-retrieval-1: "Retrieval has no entry in the LLM agent-family taxonomy and is reachable only via allowlisted tools."

    Owning slice: S-Y2 capstone. Evidence: runtime retrieval tool provider
    allowlist gate and typed rejection for hidden/unknown retrieval tool calls.
    """

    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        max_retrieval_attempts=3,
    )

    rejected = await provider.execute_tool_call(
        _call("retrieval.debug", "call-hidden", {"query": "storm"}),
        visible_tool_names=(
            WRITER_RETRIEVAL_SEARCH_TOOL,
            WRITER_RETRIEVAL_EXPAND_TOOL,
            WRITER_RETRIEVAL_USAGE_TOOL,
        ),
    )

    assert rejected.success is False
    assert rejected.error_code == "writer_retrieval_tool_not_allowed"


def test_acc11_retrieval_2_missing_usage_record_rejects_final_output_durably(
    retrieval_session,
) -> None:
    """ACC-11-retrieval-2: "Given a turn with ≥1 successful `retrieval.search` and a writer final output submitted with no `retrieval.usage` record, the final output is rejected."

    Owning slice: S-Y1 durable gate. Evidence: `test_sy1_durable_finalization_gate`
    and the durable `persist_generated_artifact` guard.
    """

    prepared = _prepare_segment_turn(retrieval_session)
    ledger = RetrievalUsageLedgerSnapshot(
        retrieval_generation=1,
        usage_generation=0,
        usage_material_id=None,
    )

    with pytest.raises(WriterFinalizationRejected) as excinfo:
        _persist(prepared, ledger)

    assert excinfo.value.reason_code == USAGE_REQUIRED_CODE


def test_acc11_retrieval_3_present_but_incomplete_usage_record_still_passes_gate(
    retrieval_session,
) -> None:
    """ACC-11-retrieval-3: "A writer-submitted usage record is stored as-is with no deterministic cross-check that 'verifies' it against actual hits (no code auto-tracking that can reject an under-report)."

    Owning slice: S-Y1 / RET-004 trust contract. Evidence: durable gate checks
    generation counters plus material kind only; the seeded usage payload is
    intentionally empty and still passes.
    """

    prepared = _prepare_segment_turn(retrieval_session)
    identity = _gate_identity(prepared.packet, prepared.runtime_identity)
    _seed_material(
        prepared.material_service,
        identity,
        material_id="retrieval_usage_incomplete",
        kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
        short_id="U1",
    )
    ledger = RetrievalUsageLedgerSnapshot(
        retrieval_generation=1,
        usage_generation=1,
        usage_material_id="retrieval_usage_incomplete",
    )

    response = _persist(prepared, ledger)

    assert response.artifact_id


def test_acc11_retrieval_4_writer_loop_stays_off_under_all_four_negative_preconditions(
    retrieval_session,
) -> None:
    """ACC-11-retrieval-4: "The writer retrieval loop does NOT run when any of {packet/profile disallows retrieval, max_attempts ≤ 0, no retrieval services, model lacks tool support} holds."

    Owning slice: S-Y2 / RET-006. Evidence: `WritingWorkerExecutionService`
    `should_buffer_stream` delegates to the same production guard that gates the
    retrieval loop before any harness run.
    """

    identity = _build_identity(retrieval_session)
    tool_gateway = _HarnessToolGateway([])

    disabled_packet = _build_packet(identity).model_copy(
        update={
            "metadata": {
                "writer_retrieval_allowed": False,
                "writer_max_retrieval_attempts": 2,
            }
        }
    )
    zero_attempt_packet = _build_packet(identity).model_copy(
        update={
            "metadata": {
                "writer_retrieval_allowed": True,
                "writer_max_retrieval_attempts": 0,
            }
        }
    )
    enabled_packet = _build_packet(identity)

    enabled_service = WritingWorkerExecutionService(
        llm_gateway=tool_gateway,
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
    )
    no_retrieval_service = WritingWorkerExecutionService(llm_gateway=tool_gateway)
    no_tool_support_service = WritingWorkerExecutionService(
        llm_gateway=_OneShotGateway(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
    )

    assert (
        enabled_service.should_buffer_stream(
            packet=disabled_packet,
            model_id="model",
            provider_id="provider",
        )
        is False
    )
    assert (
        enabled_service.should_buffer_stream(
            packet=zero_attempt_packet,
            model_id="model",
            provider_id="provider",
        )
        is False
    )
    assert (
        no_retrieval_service.should_buffer_stream(
            packet=enabled_packet,
            model_id="model",
            provider_id="provider",
        )
        is False
    )
    assert (
        no_tool_support_service.should_buffer_stream(
            packet=enabled_packet,
            model_id="model",
            provider_id="provider",
        )
        is False
    )


def test_acc11_retrieval_5_worker_side_retrieval_defaults_off_under_w5a(
    retrieval_session,
) -> None:
    """ACC-11-retrieval-5: "Under the default W5-A profile, MemoryMaintenanceWorker emits zero `retrieval.*` tool calls during K-window maintenance."

    Owning slice: S-Y2 live-green assertion. Evidence: default longform memory
    worker registration has no retrieval tools and the memory family never routes
    to the writer retrieval harness.
    """

    snapshot = _seed_and_publish_longform_snapshot(retrieval_session)
    service = WorkerRegistryService(retrieval_session)
    longform_worker = service.require_worker(
        LONGFORM_MEMORY_WORKER_ID,
        snapshot_id=snapshot.runtime_profile_snapshot_id,
    )

    assert longform_worker.descriptor.family == WorkerFamily.MEMORY_MAINTENANCE
    assert not any(
        tool.startswith("retrieval.")
        for tool in longform_worker.descriptor.tool_allowlist
    )
    assert WorkerExecutorDispatcher().resolve(WorkerFamily.MEMORY_MAINTENANCE) == (
        WorkerExecutorRoute.MEMORY_MAINTENANCE_STRUCTURED_OUTPUT
    )


@pytest.mark.asyncio
async def test_acc11_retrieval_6_writer_only_sees_short_handles_and_no_raw_hit_collection_in_packet(
    retrieval_session,
) -> None:
    """ACC-11-retrieval-6: "Every retrieval card visible to the writer carries a stable short id and no raw `hit_id`/`chunk_id`, and the full raw hit collection is absent from the writer packet."

    Owning slice: S-Y2 plus context-packet inheritance. Evidence: runtime tool
    outputs expose only short handles, and packet assembly serializes retrieval
    summaries without raw hit collections.
    """

    search_service = _FakeRetrievalSearchService(
        _FakeSearchExecution(
            output=type(
                "_Output",
                (),
                {
                    "model_dump_json": staticmethod(
                        lambda exclude_none=True: json.dumps(
                            {
                                "query": "storm",
                                "results": [
                                    {
                                        "result_id": "R1",
                                        "title": "Storm",
                                        "summary": "short summary",
                                        "excerpt": "short excerpt",
                                        "text": "short text",
                                        "section": "S1",
                                    }
                                ],
                                "warnings": [],
                            }
                        )
                    )
                },
            )(),
            materials=[],
        )
    )
    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        runtime_retrieval_search_service=search_service,
        usage_guard_service=_AllowUsageGuard(),
        max_retrieval_attempts=3,
    )

    search = await provider.execute_tool_call(
        _call(WRITER_RETRIEVAL_SEARCH_TOOL, "call-search", {"query": "storm"}),
        visible_tool_names=(WRITER_RETRIEVAL_SEARCH_TOOL,),
    )

    packet, _, _ = _build_packet_with_runtime_retrieval_context(retrieval_session)
    packet_blob = json.dumps(packet.model_dump(mode="json"), ensure_ascii=False)
    retrieval_sections = [
        section
        for section in packet.context_sections
        if section.get("label") == "retrieval_cards"
    ]

    assert '"result_id"' in search.content_text
    assert "hit_id" not in search.content_text
    assert len(retrieval_sections) == 1
    assert retrieval_sections[0]["items"] == [
        "R1 [retrieval_card] Storm Callback: A recalled storm callback matters here.",
        "X1 [retrieval_expanded_chunk] Storm Callback Expanded: Expanded detail: the seal broke during the first storm.",
    ]
    assert "raw-hit-1" not in packet_blob
    assert "raw-chunk-1" not in packet_blob
    assert "retrieval_hits" not in packet_blob
    assert "archival_hits" not in packet_blob
    assert "recall_hits" not in packet_blob


def test_acc11_retrieval_7_deferred_context_packet_owns_trim_order_oracle() -> None:
    """ACC-11-retrieval-7: "A retrieval card reaches a writer/worker packet only through context packet assembly (`retrieval_card_sections`/`retrieval_source_sections`/`retrieval_refs`), and under budget pressure retrieval/overlay is trimmed before core view and recent raw turns."

    Disposition: deferred. Reason: the packet-entry route is already proven by
    the writer/worker packet assembly tests, but the trimming-order oracle is
    owned by the context-packet slice and no retrieval-slice production test in
    this workspace proves the budget-pressure ordering without faking ownership.
    """

    pytest.xfail(
        "ACC-7 is context-packet-owned: retrieval packet entry is inherited, but "
        "the trim-order oracle belongs to the packet slice rather than retrieval."
    )


@pytest.mark.asyncio
async def test_acc11_retrieval_8_common_tool_contract_and_disallowed_calls_are_rejected():
    """ACC-11-retrieval-8: "Writer/worker/maintenance retrieval all bind to the same `retrieval.search`/`expand`/`usage` contract; disallowed tools are rejected."

    Owning slice: S-Y2. Evidence: the provider exposes exactly the shared tool
    contract and rejects non-allowlisted retrieval calls with a typed error.
    """

    provider = RuntimeRetrievalToolProvider(
        identity=_identity(),
        runtime_retrieval_card_service=_FakeRuntimeRetrievalCardService(),
        max_retrieval_attempts=3,
    )
    definitions = provider.get_openai_tool_definitions(
        visible_tool_names=(
            WRITER_RETRIEVAL_SEARCH_TOOL,
            WRITER_RETRIEVAL_EXPAND_TOOL,
            WRITER_RETRIEVAL_USAGE_TOOL,
        )
    )
    rejected = await provider.execute_tool_call(
        _call("retrieval.delete", "call-delete", {"query": "storm"}),
        visible_tool_names=(
            WRITER_RETRIEVAL_SEARCH_TOOL,
            WRITER_RETRIEVAL_EXPAND_TOOL,
            WRITER_RETRIEVAL_USAGE_TOOL,
        ),
    )

    assert [item["function"]["name"] for item in definitions] == [
        WRITER_RETRIEVAL_SEARCH_TOOL,
        WRITER_RETRIEVAL_EXPAND_TOOL,
        WRITER_RETRIEVAL_USAGE_TOOL,
    ]
    assert rejected.success is False
    assert rejected.error_code == "writer_retrieval_tool_not_allowed"


def test_acc11_retrieval_9_model_facing_search_contract_excludes_backend_controls():
    """ACC-11-retrieval-9: "`RuntimeRetrievalSearchInput` carries only query/intent (+`search_kind`); it has no model-settable source-routing/K/filter/rerank field."

    Owning slice: S-Y2. Evidence: the live schema exposes only query/mode/hints
    and rejects backend-owned controls.
    """

    schema = RuntimeRetrievalSearchInput.model_json_schema()

    assert set(schema["properties"]) == {
        "query",
        "mode",
        "lexical_anchors",
        "semantic_predicates",
    }
    assert schema["properties"]["mode"]["enum"] == [
        "entity",
        "relation",
        "semantic",
    ]
    for payload in (
        {"query": "storm", "search_kind": "archival"},
        {"query": "storm", "top_k": 8},
        {"query": "storm", "filters": {"source_families": ["foundation_entry"]}},
        {"query": "storm", "rerank": True},
        {"query": "storm", "route_weights": {"keyword": 2.0}},
    ):
        with pytest.raises(ValidationError):
            RuntimeRetrievalSearchInput.model_validate(payload)


def test_acc11_retrieval_10_normal_vs_debug_observability_split():
    """ACC-11-retrieval-10: "The normal stream for a retrieval turn shows only a concise summary; card ids/queries/usage-records/attempts appear only in detail/debug, and debug renders source titles/snippets/refs (not only ids)."

    Owning slice: S-Y4. Evidence: the runtime debug query service derives both
    normal and debug payloads from the same turn-trace materials.
    """

    trace = _turn_trace(
        [
            _card_material(),
            _usage_material(
                used=[_CARD_SHORT_ID],
                gaps=[{"query": _QUERY_TEXT, "status": "missed"}],
            ),
            _miss_material(),
        ],
        usage_refs=[{"material_id": "retrieval_usage_abc", "short_id": "U1"}],
    )
    retrieval = _build_debug_query()._retrieval_summary_with_levels(turn_trace=trace)
    normal = retrieval["render_levels"]["normal"]
    debug = retrieval["render_levels"]["debug"]

    assert normal["message"] == (
        "Reference material was used; some information gaps remained."
    )
    normal_blob = json.dumps(normal, ensure_ascii=False)
    assert _CARD_SHORT_ID not in normal_blob
    assert _QUERY_TEXT not in normal_blob
    assert "usage_records" not in normal
    assert "attempt" not in normal_blob
    assert debug["cards"][0]["payload"]["title"] == _CARD_TITLE
    assert debug["cards"][0]["payload"]["summary"] == _CARD_SUMMARY
    assert debug["cards"][0]["payload"]["excerpt"] == _CARD_EXCERPT


@pytest.mark.asyncio
async def test_acc11_retrieval_11_distinct_normalized_reason_codes_stay_separate_from_insufficiency_and_model_failure():
    """ACC-11-retrieval-11: "Failure injection test asserts distinct normalized reason codes and readable messages."

    Owning slice: S-Y3. Evidence: RET-013 keeps the internal classifier taxonomy,
    but the production-surfaced signal is the normalized reason code; category on
    receipt remains a deferred strengthening.
    """

    retrieval_failure = classify_writer_retrieval_outcome(
        _outcome(
            succeeded=False,
            tool_results=[await _real_tool_not_allowed()],
            finish_reason="tool_execution_error",
        )
    )
    insufficiency = classify_writer_retrieval_outcome(
        _outcome(
            succeeded=True,
            tool_results=[await _real_zero_hit_search()],
            finish_reason="assistant_final_text",
        )
    )
    model_failure = classify_writer_retrieval_outcome(
        _outcome(
            succeeded=False,
            tool_results=[],
            finish_reason="writer_retrieval_usage_required_before_final_output",
        )
    )

    assert retrieval_failure is not None
    assert insufficiency is not None
    assert model_failure is not None
    retrieval_failure_reason_code = retrieval_failure.reason_code
    insufficiency_reason_code = insufficiency.reason_code
    model_failure_reason_code = model_failure.reason_code

    assert retrieval_failure_reason_code
    assert insufficiency_reason_code
    assert model_failure_reason_code
    assert len(
        {
            retrieval_failure_reason_code,
            insufficiency_reason_code,
            model_failure_reason_code,
        }
    ) == 3

    surfaced_retrieval_failure = WriterRetrievalError(
        retrieval_failure_reason_code,
        "turn-retrieval-failure",
    )
    surfaced_model_failure = WriterRetrievalError(
        model_failure_reason_code,
        "turn-model-failure",
    )
    assert surfaced_retrieval_failure.code == retrieval_failure_reason_code
    assert surfaced_model_failure.code == model_failure_reason_code

    assert insufficiency.reason_code == insufficiency_reason_code
    assert retrieval_failure.reason_code != insufficiency_reason_code
    assert model_failure.reason_code != insufficiency_reason_code


def test_acc11_retrieval_12_rollback_invalidates_cards_by_turn_cutoff_without_ttl_or_version_gate(
    retrieval_session,
) -> None:
    """ACC-11-retrieval-12: "After a rollback/branch past a card's producing turn, the card is invalidated/superseded by the `anchor_turn_id` cascade, with no separate TTL/version check involved."

    Owning slice: S-Y5. Evidence: rollback invalidates runtime workspace
    materials by producing turn id; TTL/version metadata does not participate in
    the cutoff decision.
    """

    story_session, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="acc11-rollback-cascade",
        count=2,
    )
    target_identity = identities[0]
    hidden_identity = identities[1]
    workspace = _record_retrieval_card(
        retrieval_session,
        identity=target_identity,
        material_id="retrieval-card-target-turn",
        short_id="R1",
        marker="target-stale",
        ttl="expired-target-card",
        version="stale-target-version",
    )
    _record_retrieval_card(
        retrieval_session,
        identity=hidden_identity,
        material_id="retrieval-card-hidden-turn",
        short_id="R1",
        marker="hidden-fresh",
        ttl="fresh-hidden-card",
        version="current-hidden-version",
    )

    receipt = service.rollback_to_turn(
        session_id=story_session.session_id,
        target_turn_id=target_identity.turn_id,
        actor="test.acc11.rollback",
    )

    target_card = workspace.require_material(
        identity=target_identity,
        material_id="retrieval-card-target-turn",
    )
    hidden_card = workspace.require_material(
        identity=hidden_identity,
        material_id="retrieval-card-hidden-turn",
    )
    hidden_turn = retrieval_session.get(StoryTurnRecord, hidden_identity.turn_id)

    assert hidden_turn is not None
    assert hidden_turn.visibility_state == "hidden_by_rollback"
    assert target_card.lifecycle == RuntimeWorkspaceMaterialLifecycle.ACTIVE
    assert target_card.metadata["ttl"] == "expired-target-card"
    assert target_card.metadata["version"] == "stale-target-version"
    assert hidden_card.lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED
    assert hidden_card.metadata["ttl"] == "fresh-hidden-card"
    assert hidden_card.metadata["version"] == "current-hidden-version"
    assert hidden_card.metadata["visibility_state"] == "hidden_by_rollback"
    assert hidden_card.metadata["hidden_after_turn_id"] == target_identity.turn_id
    assert receipt.metadata["visibility_transition"]["invalidated_workspace_material_ids"] == [
        "retrieval-card-hidden-turn"
    ]
