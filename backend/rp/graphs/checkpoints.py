"""Shared LangGraph checkpoint helpers for RP runtime."""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import Any, Callable, Iterator

from config import get_settings


@contextmanager
def open_checkpointed_graph(compiler: Callable[[Any], Any]) -> Iterator[Any]:
    """Compile one graph against the active backend checkpoint store."""
    settings = get_settings()
    if settings.is_postgres_database:
        from langgraph.checkpoint.postgres import PostgresSaver

        with PostgresSaver.from_conn_string(settings.langgraph_checkpoint_url) as saver:
            yield compiler(saver)
        return

    from langgraph.checkpoint.sqlite import SqliteSaver

    sqlite_path = settings.langgraph_sqlite_path
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(sqlite_path)) as saver:
        yield compiler(saver)


@asynccontextmanager
async def open_async_checkpointed_graph(compiler: Callable[[Any], Any]):
    """Compile one graph against the active backend checkpoint store asynchronously."""
    settings = get_settings()
    if settings.is_postgres_database:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(
            settings.langgraph_checkpoint_url
        ) as saver:
            yield compiler(saver)
        return

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    sqlite_path = settings.langgraph_sqlite_path
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(sqlite_path)) as saver:
        yield compiler(saver)


def build_thread_config(
    *,
    thread_id: str,
    namespace: str = "",
    checkpoint_id: str | None = None,
) -> dict[str, dict[str, str]]:
    configurable: dict[str, str] = {
        "thread_id": thread_id if not namespace else f"{thread_id}:{namespace}",
        "checkpoint_ns": "",
    }
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


def snapshot_checkpoint_id(snapshot: Any) -> str | None:
    config = getattr(snapshot, "config", None) or {}
    configurable = config.get("configurable") or {}
    return configurable.get("checkpoint_id")


def snapshot_parent_checkpoint_id(snapshot: Any) -> str | None:
    parent_config = getattr(snapshot, "parent_config", None) or {}
    configurable = parent_config.get("configurable") or {}
    return configurable.get("checkpoint_id")


def snapshot_exists(snapshot: Any) -> bool:
    return getattr(snapshot, "created_at", None) is not None or bool(
        getattr(snapshot, "values", None)
    )


def require_snapshot_checkpoint_id(snapshot: Any) -> str:
    checkpoint_id = snapshot_checkpoint_id(snapshot)
    if checkpoint_id is None:
        raise RuntimeError("LangGraph snapshot did not expose a checkpoint_id")
    return checkpoint_id
