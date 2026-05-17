"""Materialize bounded retrieval cards and usage into Runtime Workspace."""

from __future__ import annotations

from itertools import count
from uuid import uuid4

from sqlmodel import Session

from rp.models.dsl import Domain, ObjectRef
from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_crud import (
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    RetrievalHit,
    RetrievalSearchResult,
)
from rp.models.retrieval_runtime_contracts import (
    RetrievalKnowledgeGapItem,
    RetrievalUsageRecordPayload,
)
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.worker_memory import WorkerSourceRefBundle

from .retrieval_broker import RetrievalBroker
from .runtime_workspace_material_service import RuntimeWorkspaceMaterialService


class RuntimeRetrievalCardServiceError(ValueError):
    """Stable retrieval-card error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class RuntimeRetrievalCardService:
    """Bounded retrieval loop over RetrievalBroker plus Runtime Workspace cards."""

    def __init__(
        self,
        *,
        retrieval_broker: RetrievalBroker | None = None,
        runtime_workspace_material_service: RuntimeWorkspaceMaterialService
        | None = None,
        session: Session | None = None,
    ) -> None:
        self._retrieval_broker = retrieval_broker
        self._runtime_workspace_material_service = runtime_workspace_material_service
        self._session = session

    async def search_recall_to_cards(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        input_model: MemorySearchRecallInput,
        actor: str,
        attempt_index: int = 1,
    ) -> tuple[
        RetrievalSearchResult,
        list[RuntimeWorkspaceMaterial],
        RuntimeWorkspaceMaterial | None,
    ]:
        result = await self._broker(identity=identity).search_recall(input_model)
        return self.materialize_search_result(
            identity=identity,
            result=result,
            actor=actor,
            query_text=input_model.query,
            search_kind="recall",
            attempt_index=attempt_index,
        )

    async def search_archival_to_cards(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        input_model: MemorySearchArchivalInput,
        actor: str,
        attempt_index: int = 1,
    ) -> tuple[
        RetrievalSearchResult,
        list[RuntimeWorkspaceMaterial],
        RuntimeWorkspaceMaterial | None,
    ]:
        result = await self._broker(identity=identity).search_archival(input_model)
        return self.materialize_search_result(
            identity=identity,
            result=result,
            actor=actor,
            query_text=input_model.query,
            search_kind="archival",
            attempt_index=attempt_index,
        )

    def materialize_search_result(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        result: RetrievalSearchResult,
        actor: str,
        query_text: str,
        search_kind: str,
        attempt_index: int = 1,
    ) -> tuple[
        RetrievalSearchResult,
        list[RuntimeWorkspaceMaterial],
        RuntimeWorkspaceMaterial | None,
    ]:
        return self._materialize_search_result(
            identity=identity,
            result=result,
            actor=actor,
            query_text=query_text,
            search_kind=search_kind,
            attempt_index=attempt_index,
        )

    def expand_cards(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        card_material_ids: list[str],
        actor: str,
    ) -> list[RuntimeWorkspaceMaterial]:
        expanded: list[RuntimeWorkspaceMaterial] = []
        card_ids = [
            str(item).strip() for item in card_material_ids if str(item).strip()
        ]
        seen: set[str] = set()
        for card_material_id in card_ids:
            if card_material_id in seen:
                continue
            seen.add(card_material_id)
            card = self._workspace().require_material(
                identity=identity,
                material_id=card_material_id,
            )
            if card.material_kind != RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD:
                raise RuntimeRetrievalCardServiceError(
                    "runtime_retrieval_expand_requires_card",
                    card_material_id,
                )
            chunk_id = str(card.payload.get("hit_id") or "").strip()
            if not chunk_id:
                raise RuntimeRetrievalCardServiceError(
                    "runtime_retrieval_card_hit_id_missing",
                    card_material_id,
                )
            expanded_payload = self._expand_card_payload(card)
            expanded.append(
                self._record_expanded_chunk(
                    identity=identity,
                    card=card,
                    expanded_payload=expanded_payload,
                    actor=actor,
                )
            )
        return expanded

    def expand_cards_by_refs(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        card_refs: list[str],
        actor: str,
    ) -> list[RuntimeWorkspaceMaterial]:
        cards = self._resolve_existing_materials(
            identity=identity,
            material_refs=card_refs,
            expected_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
        )
        return self.expand_cards(
            identity=identity,
            card_material_ids=[card.material_id for card in cards],
            actor=actor,
        )

    def record_writer_usage(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        used_card_ids: list[str],
        used_expanded_chunk_ids: list[str],
        missed_query_ids: list[str] | None = None,
        actor: str,
        knowledge_gaps: list[RetrievalKnowledgeGapItem | dict[str, object]]
        | None = None,
    ) -> RuntimeWorkspaceMaterial:
        used_cards = self._resolve_existing_materials(
            identity=identity,
            material_refs=used_card_ids,
            expected_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
        )
        used_expanded_chunks = self._resolve_existing_materials(
            identity=identity,
            material_refs=used_expanded_chunk_ids,
            expected_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK,
        )
        missed_queries = self._resolve_existing_materials(
            identity=identity,
            material_refs=missed_query_ids or [],
            expected_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_MISS,
        )
        used_card_material_ids = [material.material_id for material in used_cards]
        used_expanded_chunk_material_ids = [
            material.material_id for material in used_expanded_chunks
        ]
        missed_query_material_ids = [
            material.material_id for material in missed_queries
        ]
        parent_cards_for_used_expanded_chunks = self._parent_cards_for_expanded_chunks(
            identity=identity,
            expanded_chunks=used_expanded_chunks,
        )
        unused_cards = self._derive_unused_cards(
            identity=identity,
            used_cards=used_cards,
            parent_cards_for_used_expanded_chunks=parent_cards_for_used_expanded_chunks,
        )
        payload = RetrievalUsageRecordPayload(
            used_card_short_ids=self._material_short_ids(used_cards),
            expanded_card_short_ids=self._material_short_ids(
                parent_cards_for_used_expanded_chunks
            ),
            unused_card_short_ids=self._material_short_ids(unused_cards),
            used_card_material_ids=used_card_material_ids,
            used_expanded_chunk_material_ids=used_expanded_chunk_material_ids,
            unused_card_material_ids=[
                material.material_id for material in unused_cards
            ],
            missed_query_short_ids=self._material_short_ids(missed_queries),
            missed_query_material_ids=missed_query_material_ids,
            knowledge_gaps=self._normalize_knowledge_gaps(knowledge_gaps),
        )
        bundle = WorkerSourceRefBundle(
            retrieval_card_material_ids=used_card_material_ids,
            retrieval_expanded_chunk_material_ids=used_expanded_chunk_material_ids,
            retrieval_usage_material_ids=[],
        )
        existing = self._find_existing_usage_record(
            identity=identity,
            payload=payload,
        )
        if existing is not None:
            return existing
        payload_dict = payload.model_dump(mode="json")
        material = RuntimeWorkspaceMaterial(
            material_id=f"retrieval_usage_{uuid4().hex}",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
            identity=identity,
            domain="chapter",
            domain_path="chapter.runtime.retrieval.usage",
            short_id=self._next_short_id(
                identity=identity,
                prefix="U",
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
            ),
            payload=payload_dict,
            lifecycle=RuntimeWorkspaceMaterialLifecycle.USED,
            visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
            created_by=actor,
            source_refs=bundle.to_source_refs()
            + [
                MemorySourceRef(
                    source_type="retrieval_miss_material",
                    source_id=material_id,
                    layer="runtime_workspace",
                    metadata={"source_of_truth": False},
                )
                for material_id in missed_query_material_ids
            ],
            metadata={
                "usage_kind": "writer_explicit",
                "governed_promotion_only": True,
                "contract_version": "runtime_retrieval_usage_d2",
                "expanded_card_short_ids_population": (
                    "derived_from_used_expanded_chunk_refs_until_e2_writer_loop"
                ),
                "unused_card_derivation": (
                    "writer_visible_cards_minus_used_cards_and_parent_cards_of_used_expanded_chunks"
                ),
                "knowledge_gap_support": "structured_optional",
            },
        )
        return self._workspace().record_material(material).material

    def build_source_ref_bundle(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> WorkerSourceRefBundle:
        workspace = self._workspace()
        card_ids = [
            material.material_id
            for material in workspace.list_materials(
                identity=identity,
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            )
            if material.visibility
            == RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value
        ]
        expanded_ids = [
            material.material_id
            for material in workspace.list_materials(
                identity=identity,
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK,
            )
            if material.visibility
            == RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value
        ]
        usage_ids = [
            material.material_id
            for material in workspace.list_materials(
                identity=identity,
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
                lifecycle=RuntimeWorkspaceMaterialLifecycle.USED,
            )
        ]
        return WorkerSourceRefBundle(
            retrieval_card_material_ids=card_ids,
            retrieval_expanded_chunk_material_ids=expanded_ids,
            retrieval_usage_material_ids=usage_ids,
        )

    def list_writer_visible_context(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> list[dict[str, object]]:
        cards = self.list_writer_visible_materials(identity=identity)
        items: list[dict[str, object]] = []
        for material in cards:
            items.append(
                {
                    "material_id": material.material_id,
                    "short_id": material.short_id,
                    "kind": material.material_kind.value,
                    "domain": material.domain,
                    "domain_path": material.domain_path,
                    "summary": material.payload.get("summary")
                    or material.payload.get("excerpt")
                    or material.payload.get("text"),
                    "title": material.payload.get("title"),
                }
            )
        return items

    def list_writer_visible_materials(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> list[RuntimeWorkspaceMaterial]:
        materials = [
            *self._workspace().list_materials(
                identity=identity,
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            ),
            *self._workspace().list_materials(
                identity=identity,
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK,
            ),
        ]
        return [
            material
            for material in materials
            if material.visibility
            == RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value
        ]

    def require_material(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
    ) -> RuntimeWorkspaceMaterial:
        return self._workspace().require_material(
            identity=identity,
            material_id=material_id,
        )

    def _materialize_search_result(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        result: RetrievalSearchResult,
        actor: str,
        query_text: str,
        search_kind: str,
        attempt_index: int,
    ) -> tuple[
        RetrievalSearchResult,
        list[RuntimeWorkspaceMaterial],
        RuntimeWorkspaceMaterial | None,
    ]:
        cards = [
            self._record_card(
                identity=identity,
                hit=hit,
                actor=actor,
                search_kind=search_kind,
                query_text=query_text,
                attempt_index=attempt_index,
            )
            for hit in list(getattr(result, "hits", []))
        ]
        miss = None
        if not cards:
            miss = self._record_miss(
                identity=identity,
                query_text=query_text,
                actor=actor,
                search_kind=search_kind,
                warnings=list(getattr(result, "warnings", [])),
                attempt_index=attempt_index,
            )
        return result, cards, miss

    def _record_card(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        hit: RetrievalHit,
        actor: str,
        search_kind: str,
        query_text: str,
        attempt_index: int,
    ) -> RuntimeWorkspaceMaterial:
        material = RuntimeWorkspaceMaterial(
            material_id=f"retrieval_card_{uuid4().hex}",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=identity,
            domain=hit.domain.value,
            domain_path=hit.domain_path,
            short_id=self._next_short_id(
                identity=identity,
                prefix="R",
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            ),
            payload={
                "hit_id": hit.hit_id,
                "query_id": hit.query_id,
                "query_text": query_text,
                "search_kind": search_kind,
                "excerpt": hit.excerpt_text,
                "text": hit.excerpt_text,
                "summary": self._stored_summary_from_hit(hit),
                "summary_source": self._stored_summary_source(hit),
                "title": hit.metadata.get("title"),
                "rank": hit.rank,
                "score": hit.score,
                "knowledge_ref": (
                    hit.knowledge_ref.model_dump(mode="json")
                    if hit.knowledge_ref is not None
                    else None
                ),
                "metadata": dict(hit.metadata),
            },
            visibility=RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
            created_by=actor,
            source_refs=[
                MemorySourceRef(
                    source_type="retrieval_hit",
                    source_id=hit.hit_id,
                    layer=hit.layer,
                    domain=hit.domain.value,
                    block_id=hit.domain_path,
                    metadata={
                        "query_id": hit.query_id,
                        "score": hit.score,
                        "rank": hit.rank,
                        "provenance_refs": list(hit.provenance_refs),
                    },
                )
            ],
            metadata={
                "search_kind": search_kind,
                "query_id": hit.query_id,
                "query_text": query_text,
                "attempt_index": attempt_index,
                "retrieval_layer": hit.layer,
                "raw_dump_passthrough": False,
            },
        )
        return self._workspace().record_material(material).material

    @classmethod
    def _stored_summary_from_hit(cls, hit: RetrievalHit) -> str | None:
        source = cls._stored_summary_source(hit)
        if source is None:
            return None
        value = hit.metadata.get(source)
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _stored_summary_source(hit: RetrievalHit) -> str | None:
        for key in (
            "stored_summary",
            "entry_summary",
            "summary_text",
            "setup_summary",
            "summary",
            "document_summary",
        ):
            value = hit.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return key
        return None

    def _record_expanded_chunk(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        card: RuntimeWorkspaceMaterial,
        expanded_payload: dict[str, object],
        actor: str,
    ) -> RuntimeWorkspaceMaterial:
        metadata_payload = expanded_payload.get("metadata")
        metadata = dict(metadata_payload) if isinstance(metadata_payload, dict) else {}
        provenance_refs_payload = expanded_payload.get("provenance_refs")
        provenance_refs = (
            list(provenance_refs_payload)
            if isinstance(provenance_refs_payload, list)
            else []
        )
        material = RuntimeWorkspaceMaterial(
            material_id=f"retrieval_expanded_{uuid4().hex}",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK,
            identity=identity,
            domain=str(expanded_payload["domain"]),
            domain_path=(
                str(expanded_payload["domain_path"])
                if expanded_payload.get("domain_path") is not None
                else None
            ),
            short_id=self._next_short_id(
                identity=identity,
                prefix="X",
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK,
            ),
            payload={
                "card_material_id": card.material_id,
                "card_short_id": card.short_id,
                "chunk_id": expanded_payload["chunk_id"],
                "chunk_index": expanded_payload["chunk_index"],
                "title": expanded_payload.get("title"),
                "summary": str(expanded_payload["text"])[:220],
                "text": expanded_payload["text"],
                "token_count": expanded_payload.get("token_count"),
                "metadata": metadata,
            },
            lifecycle=RuntimeWorkspaceMaterialLifecycle.EXPANDED,
            visibility=RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
            created_by=actor,
            source_refs=[
                MemorySourceRef(
                    source_type="retrieval_card_material",
                    source_id=card.material_id,
                    layer="runtime_workspace",
                    domain=card.domain,
                    entry_id=card.material_id,
                ),
                MemorySourceRef(
                    source_type="knowledge_chunk",
                    source_id=str(expanded_payload["chunk_id"]),
                    layer="retrieval_core",
                    domain=str(expanded_payload["domain"]),
                    block_id=(
                        str(expanded_payload["domain_path"])
                        if expanded_payload.get("domain_path") is not None
                        else None
                    ),
                    metadata={
                        "asset_id": expanded_payload.get("asset_id"),
                        "parsed_document_id": expanded_payload.get(
                            "parsed_document_id"
                        ),
                        "provenance_refs": provenance_refs,
                    },
                ),
            ],
            metadata={
                "expanded_from_card_material_id": card.material_id,
                "expanded_from_card_short_id": card.short_id,
                "raw_dump_passthrough": False,
            },
        )
        return self._workspace().record_material(material).material

    def _record_miss(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        query_text: str,
        actor: str,
        search_kind: str,
        warnings: list[str],
        attempt_index: int,
    ) -> RuntimeWorkspaceMaterial:
        material = RuntimeWorkspaceMaterial(
            material_id=f"retrieval_miss_{uuid4().hex}",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_MISS,
            identity=identity,
            domain="chapter",
            domain_path="chapter.runtime.retrieval.miss",
            short_id=self._next_short_id(
                identity=identity,
                prefix="M",
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_MISS,
            ),
            payload={
                "query": query_text,
                "query_text": query_text,
                "search_kind": search_kind,
                "attempt_index": attempt_index,
                "miss_reason": "search_no_hit",
                "warnings": list(warnings),
            },
            visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
            created_by=actor,
            metadata={
                "miss_kind": "search_no_hit",
                "attempt_index": attempt_index,
            },
        )
        return self._workspace().record_material(material).material

    def _next_short_id(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        prefix: str,
        material_kind: RuntimeWorkspaceMaterialKind,
    ) -> str:
        materials = self._workspace().list_materials(
            identity=identity,
            material_kind=material_kind,
        )
        used = {
            str(material.short_id or "").strip().upper()
            for material in materials
            if material.short_id
        }
        for index in count(1):
            candidate = f"{prefix}{index}"
            if candidate.upper() not in used:
                return candidate
        raise AssertionError("unreachable")

    def _resolve_existing_materials(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_refs: list[str],
        expected_kind: RuntimeWorkspaceMaterialKind,
    ) -> list[RuntimeWorkspaceMaterial]:
        materials_by_short_id = {
            str(material.short_id or "").strip().upper(): material
            for material in self._workspace().list_materials(
                identity=identity,
                material_kind=expected_kind,
            )
            if material.short_id
        }
        normalized: list[str] = []
        resolved: list[RuntimeWorkspaceMaterial] = []
        seen: set[str] = set()
        for material_ref in material_refs:
            value = str(material_ref or "").strip()
            if not value or value in seen:
                continue
            material = self._workspace().get_material(
                identity=identity,
                material_id=value,
            )
            if material is None:
                material = materials_by_short_id.get(value.upper())
                if material is None:
                    raise RuntimeRetrievalCardServiceError(
                        "runtime_retrieval_material_reference_not_found",
                        value,
                    )
            elif material.material_kind != expected_kind:
                raise RuntimeRetrievalCardServiceError(
                    "runtime_retrieval_material_kind_mismatch",
                    value,
                )
            seen.add(value)
            if material.material_id in normalized:
                continue
            normalized.append(material.material_id)
            resolved.append(material)
        return resolved

    def _workspace(self) -> RuntimeWorkspaceMaterialService:
        if self._runtime_workspace_material_service is not None:
            return self._runtime_workspace_material_service
        return RuntimeWorkspaceMaterialService(session=self._session)

    def _find_existing_usage_record(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        payload: RetrievalUsageRecordPayload,
    ) -> RuntimeWorkspaceMaterial | None:
        payload_dict = payload.model_dump(mode="json")
        for material in self._workspace().list_materials(
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
        ):
            if dict(material.payload or {}) == payload_dict:
                return material
        return None

    def _derive_unused_cards(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        used_cards: list[RuntimeWorkspaceMaterial],
        parent_cards_for_used_expanded_chunks: list[RuntimeWorkspaceMaterial],
    ) -> list[RuntimeWorkspaceMaterial]:
        consumed_card_ids = {material.material_id for material in used_cards} | {
            material.material_id for material in parent_cards_for_used_expanded_chunks
        }
        return [
            material
            for material in self.list_writer_visible_materials(identity=identity)
            if material.material_kind == RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD
            and material.material_id not in consumed_card_ids
        ]

    def _parent_cards_for_expanded_chunks(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        expanded_chunks: list[RuntimeWorkspaceMaterial],
    ) -> list[RuntimeWorkspaceMaterial]:
        parents: list[RuntimeWorkspaceMaterial] = []
        seen: set[str] = set()
        for material in expanded_chunks:
            card_material_id = str(
                material.payload.get("card_material_id") or ""
            ).strip()
            if not card_material_id:
                raise RuntimeRetrievalCardServiceError(
                    "runtime_retrieval_expanded_chunk_card_missing",
                    material.material_id,
                )
            if card_material_id in seen:
                continue
            seen.add(card_material_id)
            parent = self._workspace().require_material(
                identity=identity,
                material_id=card_material_id,
            )
            if parent.material_kind != RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD:
                raise RuntimeRetrievalCardServiceError(
                    "runtime_retrieval_material_kind_mismatch",
                    card_material_id,
                )
            parents.append(parent)
        return parents

    def _material_short_ids(
        self,
        materials: list[RuntimeWorkspaceMaterial],
    ) -> list[str]:
        short_ids: list[str] = []
        seen: set[str] = set()
        for material in materials:
            short_id = str(material.short_id or "").strip()
            if not short_id:
                raise RuntimeRetrievalCardServiceError(
                    "runtime_retrieval_material_short_id_missing",
                    material.material_id,
                )
            if short_id in seen:
                continue
            seen.add(short_id)
            short_ids.append(short_id)
        return short_ids

    @staticmethod
    def _normalize_knowledge_gaps(
        knowledge_gaps: list[RetrievalKnowledgeGapItem | dict[str, object]] | None,
    ) -> list[RetrievalKnowledgeGapItem]:
        normalized: list[RetrievalKnowledgeGapItem] = []
        for index, item in enumerate(knowledge_gaps or [], start=1):
            gap = (
                item
                if isinstance(item, RetrievalKnowledgeGapItem)
                else RetrievalKnowledgeGapItem.model_validate(item)
            )
            if gap.gap_id is None:
                gap = gap.model_copy(update={"gap_id": f"G{index}"})
            normalized.append(gap)
        return normalized

    def _broker(self, *, identity: MemoryRuntimeIdentity) -> RetrievalBroker:
        if self._retrieval_broker is not None:
            return self._retrieval_broker
        return RetrievalBroker(
            default_story_id=identity.story_id,
            runtime_identity=identity,
            session=self._session,
        )

    def _expand_card_payload(self, card: RuntimeWorkspaceMaterial) -> dict[str, object]:
        hit = self._hit_from_card(card)
        return self._broker(identity=card.identity).expand_hit(hit)

    @staticmethod
    def _hit_from_card(card: RuntimeWorkspaceMaterial) -> RetrievalHit:
        knowledge_ref_payload = card.payload.get("knowledge_ref")
        knowledge_ref_layer = None
        if isinstance(knowledge_ref_payload, dict):
            raw_layer = knowledge_ref_payload.get("layer")
            knowledge_ref_layer = str(raw_layer).strip() if raw_layer else None
        return RetrievalHit(
            hit_id=str(card.payload.get("hit_id") or ""),
            query_id=str(card.payload.get("query_id") or ""),
            layer=str(
                card.metadata.get("retrieval_layer") or knowledge_ref_layer or ""
            ),
            domain=Domain(card.domain),
            domain_path=card.domain_path,
            knowledge_ref=(
                ObjectRef.model_validate(knowledge_ref_payload)
                if isinstance(knowledge_ref_payload, dict)
                else None
            ),
            excerpt_text=str(
                card.payload.get("excerpt") or card.payload.get("summary") or ""
            ),
            score=float(card.payload.get("score") or 0.0),
            rank=int(card.payload.get("rank") or 0),
            metadata=dict(card.payload.get("metadata") or {}),
            provenance_refs=[],
        )
