"""Persistence service for retrieval source assets and parsed documents."""

from __future__ import annotations

from sqlmodel import select

from models.rp_retrieval_store import ParsedDocumentRecord, SourceAssetRecord
from rp.models.retrieval_records import ParsedDocument, ParsedDocumentSection, SourceAsset


class RetrievalDocumentService:
    """Manage SourceAsset and ParsedDocument records."""

    def __init__(self, session) -> None:
        self._session = session

    def get_source_asset(self, asset_id: str) -> SourceAsset | None:
        record = self._session.get(SourceAssetRecord, asset_id)
        return self._record_to_source_asset(record) if record is not None else None

    def upsert_source_asset(self, asset: SourceAsset) -> SourceAsset:
        record = self._session.get(SourceAssetRecord, asset.asset_id)
        payload = {
            "story_id": asset.story_id,
            "mode": asset.mode.value,
            "collection_id": asset.collection_id,
            "workspace_id": asset.workspace_id,
            "step_id": asset.step_id,
            "commit_id": asset.commit_id,
            "asset_kind": asset.asset_kind,
            "source_ref": asset.source_ref,
            "title": asset.title,
            "storage_path": asset.storage_path,
            "mime_type": asset.mime_type,
            "raw_excerpt": asset.raw_excerpt,
            "parse_status": asset.parse_status,
            "ingestion_status": asset.ingestion_status,
            "mapped_targets_json": list(asset.mapped_targets),
            "metadata_json": dict(asset.metadata),
            "updated_at": asset.updated_at,
        }
        if record is None:
            record = SourceAssetRecord(
                asset_id=asset.asset_id,
                created_at=asset.created_at,
                **payload,
            )
        else:
            for field_name, value in payload.items():
                setattr(record, field_name, value)
        self._session.add(record)
        return self._record_to_source_asset(record)

    def list_story_assets(self, story_id: str) -> list[SourceAsset]:
        stmt = select(SourceAssetRecord).where(SourceAssetRecord.story_id == story_id)
        return [self._record_to_source_asset(record) for record in self._session.exec(stmt).all()]

    def save_parsed_document(self, document: ParsedDocument) -> ParsedDocument:
        record = self._session.get(ParsedDocumentRecord, document.parsed_document_id)
        payload = {
            "asset_id": document.asset_id,
            "story_id": self.get_source_asset(document.asset_id).story_id,
            "parser_kind": document.parser_kind,
            "document_structure_json": [
                section.model_dump(mode="json") for section in document.document_structure
            ],
            "parse_warnings_json": list(document.parse_warnings),
            "updated_at": document.updated_at,
        }
        if record is None:
            record = ParsedDocumentRecord(
                parsed_document_id=document.parsed_document_id,
                created_at=document.created_at,
                **payload,
            )
        else:
            for field_name, value in payload.items():
                setattr(record, field_name, value)
        self._session.add(record)
        return self._record_to_parsed_document(record)

    def get_parsed_document(self, parsed_document_id: str) -> ParsedDocument | None:
        record = self._session.get(ParsedDocumentRecord, parsed_document_id)
        return self._record_to_parsed_document(record) if record is not None else None

    def get_parsed_document_by_asset(self, asset_id: str) -> ParsedDocument | None:
        stmt = (
            select(ParsedDocumentRecord)
            .where(ParsedDocumentRecord.asset_id == asset_id)
            .order_by(ParsedDocumentRecord.updated_at.desc())
        )
        record = self._session.exec(stmt).first()
        return self._record_to_parsed_document(record) if record is not None else None

    @staticmethod
    def _record_to_source_asset(record: SourceAssetRecord) -> SourceAsset:
        return SourceAsset.model_validate(
            {
                "asset_id": record.asset_id,
                "story_id": record.story_id,
                "mode": record.mode,
                "workspace_id": record.workspace_id,
                "step_id": record.step_id,
                "commit_id": record.commit_id,
                "asset_kind": record.asset_kind,
                "source_ref": record.source_ref,
                "title": record.title,
                "storage_path": record.storage_path,
                "mime_type": record.mime_type,
                "raw_excerpt": record.raw_excerpt,
                "parse_status": record.parse_status,
                "ingestion_status": record.ingestion_status,
                "collection_id": record.collection_id,
                "mapped_targets": record.mapped_targets_json,
                "metadata": record.metadata_json,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        )

    @staticmethod
    def _record_to_parsed_document(record: ParsedDocumentRecord) -> ParsedDocument:
        return ParsedDocument.model_validate(
            {
                "parsed_document_id": record.parsed_document_id,
                "asset_id": record.asset_id,
                "parser_kind": record.parser_kind,
                "document_structure": [
                    ParsedDocumentSection.model_validate(item).model_dump(mode="json")
                    for item in record.document_structure_json
                ],
                "parse_warnings": record.parse_warnings_json,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        )
