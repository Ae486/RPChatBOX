"""SQLModel database foundation for backend true-source persistence."""
from __future__ import annotations

from functools import lru_cache

from sqlmodel import Session, SQLModel, create_engine

from config import get_settings


@lru_cache
def get_engine():
    """Return the singleton SQLAlchemy engine for backend persistence."""
    settings = get_settings()
    connect_args: dict[str, object] = {}
    if settings.resolved_database_url.startswith("sqlite:///"):
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.resolved_database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


def create_db_and_tables() -> None:
    """Initialize database tables for backend-owned durable state."""
    # Import models here so SQLModel metadata is fully registered before create_all.
    from models.conversation_store import ConversationRecord, ConversationSettingsRecord

    _ = ConversationRecord, ConversationSettingsRecord
    SQLModel.metadata.create_all(get_engine())


def get_session():
    """Yield a SQLModel session for FastAPI dependencies."""
    with Session(get_engine()) as session:
        yield session
