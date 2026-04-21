"""Collection lifecycle service for retrieval-core."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from models.rp_retrieval_store import KnowledgeCollectionRecord
from rp.models.retrieval_records import KnowledgeCollection


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RetrievalCollectionService:
    """Manage retrieval collections without introducing parallel setup state."""

    def __init__(self, session) -> None:
        self._session = session

    def get_collection(self, collection_id: str) -> KnowledgeCollection | None:
        record = self._session.get(KnowledgeCollectionRecord, collection_id)
        return self._record_to_model(record) if record is not None else None

    def ensure_story_collection(
        self,
        *,
        story_id: str,
        scope: str,
        collection_kind: str,
    ) -> KnowledgeCollection:
        collection_id = f"{story_id}:{collection_kind}"
        now = _utcnow()
        record = self._session.get(KnowledgeCollectionRecord, collection_id)
        if record is None:
            record = KnowledgeCollectionRecord(
                collection_id=collection_id,
                story_id=story_id,
                scope=scope,
                collection_kind=collection_kind,
                metadata_json={"created_by": "retrieval_core"},
                created_at=now,
                updated_at=now,
            )
        else:
            record.scope = scope
            record.collection_kind = collection_kind
            record.updated_at = now
        self._session.add(record)
        return self._record_to_model(record)

    def list_story_collections(self, story_id: str) -> list[KnowledgeCollection]:
        stmt = select(KnowledgeCollectionRecord).where(KnowledgeCollectionRecord.story_id == story_id)
        return [self._record_to_model(record) for record in self._session.exec(stmt).all()]

    @staticmethod
    def _record_to_model(record: KnowledgeCollectionRecord) -> KnowledgeCollection:
        return KnowledgeCollection.model_validate(
            {
                "collection_id": record.collection_id,
                "story_id": record.story_id,
                "scope": record.scope,
                "collection_kind": record.collection_kind,
                "metadata": record.metadata_json,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        )
