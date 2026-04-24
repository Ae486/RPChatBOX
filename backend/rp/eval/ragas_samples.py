"""RAGAS sample builders for RP retrieval/RAG evaluation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import EvalArtifact, EvalRunResult


class RagasRetrievalSample(BaseModel):
    """Project-normalized retrieval/RAG sample before handing to RAGAS."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str
    case_id: str
    query: str
    retrieved_contexts: list[str] = Field(default_factory=list)
    response: str | None = None
    reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_ragas_sample_from_eval_result(
    result: EvalRunResult,
    *,
    response: str | None = None,
    reference: str | None = None,
) -> RagasRetrievalSample:
    """Build one RAGAS-ready sample from a retrieval eval run result."""
    if result.case.scope != "retrieval":
        raise ValueError(
            f"RAGAS retrieval sample requires retrieval scope, got {result.case.scope!r}"
        )
    retrieval_result = _artifact_payload(result.artifacts, kind="retrieval_result")
    retrieval_truth = _artifact_payload(result.artifacts, kind="retrieval_truth")
    return _build_ragas_sample_from_retrieval_payloads(
        case_id=result.case.case_id,
        run_id=result.run.run_id,
        trace_id=result.run.trace_id,
        retrieval_result=retrieval_result,
        retrieval_truth=retrieval_truth,
        response=response,
        reference=reference,
    )


def build_ragas_sample_from_replay_payload(
    replay_payload: dict[str, Any],
    *,
    response: str | None = None,
    reference: str | None = None,
) -> RagasRetrievalSample:
    """Build one RAGAS-ready sample from a replay payload."""
    sampled_trace = replay_payload.get("sampled_trace")
    if isinstance(sampled_trace, dict):
        sample_id = str(
            sampled_trace.get("sample_id")
            or ((replay_payload.get("source") or {}).get("sample_id"))
            or ((replay_payload.get("run") or {}).get("run_id"))
            or "sampled-replay"
        )
        case_id = str((replay_payload.get("case") or {}).get("case_id") or f"retrieval.sampled.{sample_id}")
        metadata = dict(sampled_trace.get("metadata") or {})
        if "run_id" not in metadata and isinstance(replay_payload.get("run"), dict):
            metadata["run_id"] = replay_payload["run"].get("run_id")
        if "trace_id" not in metadata and isinstance(replay_payload.get("run"), dict):
            metadata["trace_id"] = replay_payload["run"].get("trace_id")
        return RagasRetrievalSample(
            sample_id=sample_id,
            case_id=case_id,
            query=str(sampled_trace.get("query") or ""),
            retrieved_contexts=[
                str(item)
                for item in (sampled_trace.get("retrieved_contexts") or [])
                if str(item).strip()
            ],
            response=(
                response
                if response is not None
                else (str(sampled_trace.get("response")) if sampled_trace.get("response") is not None else None)
            ),
            reference=(
                reference
                if reference is not None
                else (str(sampled_trace.get("reference")) if sampled_trace.get("reference") is not None else None)
            ),
            metadata=metadata,
        )

    case = replay_payload.get("case")
    if not isinstance(case, dict) or str(case.get("scope") or "") != "retrieval":
        raise ValueError("RAGAS replay sample requires a retrieval replay payload")
    artifacts = replay_payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Replay payload missing retrieval artifacts")
    retrieval_result = _artifact_payload_from_replay(artifacts, kind="retrieval_result")
    retrieval_truth = _artifact_payload_from_replay(artifacts, kind="retrieval_truth")
    run = replay_payload.get("run")
    if not isinstance(run, dict):
        run = {}
    return _build_ragas_sample_from_retrieval_payloads(
        case_id=str(case.get("case_id") or "retrieval.replay"),
        run_id=str(run.get("run_id") or "replay-run"),
        trace_id=str(run.get("trace_id") or ""),
        retrieval_result=retrieval_result,
        retrieval_truth=retrieval_truth,
        response=response,
        reference=reference,
    )


def ragas_sample_to_dict(sample: RagasRetrievalSample) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user_input": sample.query,
        "retrieved_contexts": list(sample.retrieved_contexts),
    }
    if sample.response is not None:
        payload["response"] = sample.response
    if sample.reference is not None:
        payload["reference"] = sample.reference
    return payload


def build_ragas_dataset_payload(
    samples: list[RagasRetrievalSample],
) -> list[dict[str, Any]]:
    return [ragas_sample_to_dict(sample) for sample in samples]


def _artifact_payload(
    artifacts: list[EvalArtifact],
    *,
    kind: str,
) -> dict[str, Any]:
    artifact = next((item for item in artifacts if item.kind == kind), None)
    if artifact is None:
        raise ValueError(f"Required artifact missing for RAGAS sample: {kind}")
    return dict(artifact.payload)


def _artifact_payload_from_replay(
    artifacts: list[dict[str, Any]],
    *,
    kind: str,
) -> dict[str, Any]:
    artifact = next(
        (
            item for item in artifacts
            if isinstance(item, dict) and str(item.get("kind") or "") == kind
        ),
        None,
    )
    if artifact is None:
        raise ValueError(f"Required replay artifact missing for RAGAS sample: {kind}")
    payload = artifact.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"Replay artifact payload is not an object: {kind}")
    return dict(payload)


def _build_ragas_sample_from_retrieval_payloads(
    *,
    case_id: str,
    run_id: str,
    trace_id: str,
    retrieval_result: dict[str, Any],
    retrieval_truth: dict[str, Any],
    response: str | None,
    reference: str | None,
) -> RagasRetrievalSample:
    query_input = retrieval_result.get("query_input")
    if not isinstance(query_input, dict):
        query_input = {}
    query_result = retrieval_result.get("query_result")
    if not isinstance(query_result, dict):
        query_result = {}
    hits = query_result.get("hits")
    if not isinstance(hits, list):
        hits = []
    trace = query_result.get("trace")
    if not isinstance(trace, dict):
        trace = {}

    sample_id = f"{case_id}:{run_id}"
    query_text = str(query_input.get("text_query") or query_result.get("query") or "")
    retrieved_contexts = [_hit_to_context(hit) for hit in hits if isinstance(hit, dict)]
    if response is None:
        response = _default_response_from_query_result(query_result)
    if reference is None:
        reference = _default_reference_from_truth(
            retrieval_truth=retrieval_truth,
            query_text=query_text,
        )
    if reference is None:
        reference = next(
            (item for item in retrieved_contexts if isinstance(item, str) and item.strip()),
            response,
        )

    return RagasRetrievalSample(
        sample_id=sample_id,
        case_id=case_id,
        query=query_text,
        retrieved_contexts=retrieved_contexts,
        response=response,
        reference=reference,
        metadata={
            "run_id": run_id,
            "trace_id": trace_id,
            "story_id": retrieval_result.get("story_id"),
            "workspace_id": retrieval_result.get("workspace_id"),
            "commit_id": retrieval_result.get("commit_id"),
            "query_kind": query_input.get("query_kind"),
            "top_k": query_input.get("top_k"),
            "domains": query_input.get("domains") or [],
            "rerank": query_input.get("rerank"),
            "retrieval_route": trace.get("route"),
            "retrieval_result_kind": trace.get("result_kind"),
            "pipeline_stages": trace.get("pipeline_stages") or [],
            "returned_count": trace.get("returned_count"),
            "retrieval_warnings": query_result.get("warnings") or [],
        },
    )


def _hit_to_context(hit: dict[str, Any]) -> str:
    metadata = hit.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    contextual_text = str(metadata.get("contextual_text") or "").strip()
    excerpt_text = str(hit.get("excerpt_text") or "").strip()
    title = str(metadata.get("title") or metadata.get("document_title") or "").strip()
    domain_path = str(hit.get("domain_path") or "").strip()
    if contextual_text:
        return contextual_text
    header_parts = [part for part in [title, domain_path] if part]
    if header_parts and excerpt_text:
        return f"{' :: '.join(header_parts)}\n{excerpt_text}"
    return excerpt_text


def _default_response_from_query_result(query_result: dict[str, Any]) -> str | None:
    hits = query_result.get("hits")
    if not isinstance(hits, list) or not hits:
        return None
    first_hit = hits[0]
    if not isinstance(first_hit, dict):
        return None
    return str(first_hit.get("excerpt_text") or "").strip() or None


def _default_reference_from_truth(
    *,
    retrieval_truth: dict[str, Any],
    query_text: str,
) -> str | None:
    chunks = retrieval_truth.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        return None
    lowered_query = query_text.lower()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        lowered_text = text.lower()
        if lowered_query and any(token for token in lowered_query.split() if token in lowered_text):
            return text
    first_chunk = chunks[0]
    if not isinstance(first_chunk, dict):
        return None
    return str(first_chunk.get("text") or "").strip() or None
