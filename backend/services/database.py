"""SQLModel database foundation for backend true-source persistence."""

from __future__ import annotations

from functools import lru_cache

from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import NullPool

from config import get_settings


@lru_cache
def get_engine():
    """Return the singleton SQLAlchemy engine for backend persistence."""
    settings = get_settings()
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
    if settings.resolved_database_url.startswith("sqlite:///"):
        connect_args["check_same_thread"] = False
        # Desktop/backend local SQLite sees bursty parallel reads plus long-lived
        # streaming sessions. QueuePool easily saturates in that shape, so use
        # one-shot connections instead of a tiny bounded pool.
        engine_kwargs["poolclass"] = NullPool
    return create_engine(
        settings.resolved_database_url,
        connect_args=connect_args,
        **engine_kwargs,
    )


def create_db_and_tables() -> None:
    """Initialize database tables for backend-owned durable state."""
    # Import models here so SQLModel metadata is fully registered before create_all.
    from models.conversation_store import (
        ConversationAttachmentRecord,
        ConversationCompactSummaryRecord,
        ConversationRecord,
        ConversationSourceGraphRecord,
        ConversationSettingsRecord,
        ConversationSourceVisibilityRecord,
    )
    from models.custom_role import CustomRoleRecord
    from models.rp_memory_store import (
        MemoryApplyReceiptRecord,
        MemoryApplyTargetLinkRecord,
        MemoryProposalRecord,
        ensure_memory_store_compatible_schema,
    )
    from models.rp_core_state_store import (
        CoreStateAuthoritativeObjectRecord,
        CoreStateAuthoritativeRevisionRecord,
        CoreStateProjectionSlotRecord,
        CoreStateProjectionSlotRevisionRecord,
        ensure_core_state_store_compatible_schema,
    )
    from models.rp_retrieval_store import (
        EmbeddingRecordRecord,
        IndexJobRecord,
        KnowledgeChunkRecord,
        KnowledgeCollectionRecord,
        ParsedDocumentRecord,
        SourceAssetRecord,
        ensure_retrieval_store_compatible_schema,
    )
    from models.rp_setup_store import (
        SetupAcceptedCommitRecord,
        SetupAgentRuntimeStateRecord,
        SetupCommitProposalRecord,
        SetupDraftBlockRecord,
        SetupImportedAssetRecord,
        SetupOpenQuestionRecord,
        SetupPendingUserEditDeltaRecord,
        SetupRetrievalIngestionJobRecord,
        SetupStepAssetBindingRecord,
        SetupStepStateRecord,
        SetupWorkspaceRecord,
        ensure_setup_store_compatible_schema,
    )
    from models.rp_story_store import (
        ChapterWorkspaceRecord,
        StoryArtifactRecord,
        StoryBlockConsumerStateRecord,
        StoryDiscussionEntryRecord,
        StorySessionRecord,
        ensure_story_store_compatible_schema,
    )

    _ = (
        ConversationAttachmentRecord,
        ConversationCompactSummaryRecord,
        ConversationRecord,
        ConversationSourceGraphRecord,
        ConversationSettingsRecord,
        ConversationSourceVisibilityRecord,
        CustomRoleRecord,
        SetupWorkspaceRecord,
        SetupStepStateRecord,
        SetupDraftBlockRecord,
        SetupImportedAssetRecord,
        SetupStepAssetBindingRecord,
        SetupAgentRuntimeStateRecord,
        SetupCommitProposalRecord,
        SetupAcceptedCommitRecord,
        SetupPendingUserEditDeltaRecord,
        SetupOpenQuestionRecord,
        SetupRetrievalIngestionJobRecord,
        StorySessionRecord,
        ChapterWorkspaceRecord,
        StoryArtifactRecord,
        StoryBlockConsumerStateRecord,
        StoryDiscussionEntryRecord,
        MemoryProposalRecord,
        MemoryApplyReceiptRecord,
        MemoryApplyTargetLinkRecord,
        CoreStateAuthoritativeObjectRecord,
        CoreStateAuthoritativeRevisionRecord,
        CoreStateProjectionSlotRecord,
        CoreStateProjectionSlotRevisionRecord,
        KnowledgeCollectionRecord,
        SourceAssetRecord,
        ParsedDocumentRecord,
        KnowledgeChunkRecord,
        EmbeddingRecordRecord,
        IndexJobRecord,
    )
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    ensure_setup_store_compatible_schema(engine)
    ensure_memory_store_compatible_schema(engine)
    ensure_core_state_store_compatible_schema(engine)
    ensure_retrieval_store_compatible_schema(engine)
    ensure_story_store_compatible_schema(engine)


def get_session():
    """Yield a SQLModel session for FastAPI dependencies."""
    with Session(get_engine()) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
