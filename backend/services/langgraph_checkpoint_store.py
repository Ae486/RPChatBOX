"""LangGraph checkpoint schema helpers."""
from __future__ import annotations

import logging

from config import get_settings

logger = logging.getLogger(__name__)


def ensure_langgraph_checkpoint_schema() -> None:
    """Initialize LangGraph checkpoint persistence for the active backend store."""
    settings = get_settings()
    if settings.is_postgres_database:
        dsn = settings.langgraph_checkpoint_url
        if not dsn:
            return
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as exc:
            raise RuntimeError(
                "langgraph-checkpoint-postgres is required when using a PostgreSQL backend."
            ) from exc

        with PostgresSaver.from_conn_string(dsn) as saver:
            saver.setup()
        logger.info("LangGraph PostgreSQL checkpoint schema ensured.")
        logger.info(
            "LangGraph checkpoint persistence initialized using PostgreSQL."
        )
        return

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph SQLite checkpoint support is unavailable in the current environment."
        ) from exc

    sqlite_path = settings.langgraph_sqlite_path
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(sqlite_path)) as saver:
        saver.setup()
    logger.info("LangGraph SQLite checkpoint schema ensured at %s.", sqlite_path)
