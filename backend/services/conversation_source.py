"""LangGraph-backed source-thread service for conversations."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from typing import Annotated, Any, Iterator
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from sqlmodel import Session
from typing_extensions import TypedDict

from config import get_settings
from models.conversation_source import (
    ConversationSourceCheckpointSummary,
    ConversationSourceMessage,
    ConversationSourcePatchRequest,
    ConversationSourceSelectionRequest,
    ConversationSourceSummary,
    ConversationSourceWriteRequest,
)
from services.conversation_store import ConversationStoreService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _SourceState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _persist_source_state(state: _SourceState) -> dict[str, object]:
    """No-op node used only to anchor LangGraph checkpoint updates."""
    _ = state
    return {}


class ConversationSourceCheckpointNotFoundError(ValueError):
    """Raised when a requested checkpoint does not exist for the thread."""


class ConversationSourceMessageNotFoundError(ValueError):
    """Raised when a requested message does not exist in the selected checkpoint."""


class ConversationSourceService:
    """Persist and read source-thread state through LangGraph checkpoints."""

    def __init__(self, session: Session):
        self._session = session
        self._conversation_store = ConversationStoreService(session)

    def get_source(
        self,
        conversation_id: UUID,
        *,
        checkpoint_id: str | None = None,
    ) -> ConversationSourceSummary | None:
        record = self._conversation_store.get_conversation(conversation_id)
        if record is None:
            return None

        selected_checkpoint_id = (
            checkpoint_id
            or record.selected_checkpoint_id
            or record.latest_checkpoint_id
        )
        with self._open_graph() as graph:
            snapshot = self._get_snapshot(
                graph,
                conversation_id=conversation_id,
                checkpoint_id=selected_checkpoint_id,
            )

        return ConversationSourceSummary(
            conversation_id=conversation_id,
            checkpoint_id=self._snapshot_checkpoint_id(snapshot),
            latest_checkpoint_id=record.latest_checkpoint_id,
            selected_checkpoint_id=selected_checkpoint_id or record.selected_checkpoint_id,
            messages=self._serialize_messages(snapshot.values.get("messages", [])),
        )

    def list_history(
        self,
        conversation_id: UUID,
    ) -> list[ConversationSourceCheckpointSummary] | None:
        record = self._conversation_store.get_conversation(conversation_id)
        if record is None:
            return None

        with self._open_graph() as graph:
            history = list(graph.get_state_history(self._thread_config(conversation_id)))

        summaries: list[ConversationSourceCheckpointSummary] = []
        for snapshot in history:
            checkpoint_id = self._snapshot_checkpoint_id(snapshot)
            if checkpoint_id is None:
                continue
            messages = snapshot.values.get("messages", [])
            last_message = messages[-1] if messages else None
            summaries.append(
                ConversationSourceCheckpointSummary(
                    checkpoint_id=checkpoint_id,
                    parent_checkpoint_id=self._parent_checkpoint_id(snapshot),
                    source=(snapshot.metadata or {}).get("source"),
                    step=(snapshot.metadata or {}).get("step"),
                    created_at=self._parse_snapshot_time(snapshot.created_at),
                    message_count=len(messages),
                    last_message_id=getattr(last_message, "id", None),
                    last_message_role=self._message_role(last_message)
                    if last_message is not None
                    else None,
                    last_message_preview=self._message_preview(last_message)
                    if last_message is not None
                    else None,
                )
            )
        return summaries

    def append_messages(
        self,
        conversation_id: UUID,
        payload: ConversationSourceWriteRequest,
    ) -> ConversationSourceSummary | None:
        record = self._conversation_store.get_conversation(conversation_id)
        if record is None:
            return None

        lc_messages = [self._build_langchain_message(message) for message in payload.messages]
        target_checkpoint_id: str
        with self._open_graph() as graph:
            base_checkpoint_id = self._resolve_base_checkpoint_id(
                record.selected_checkpoint_id,
                record.latest_checkpoint_id,
                payload.base_checkpoint_id,
            )
            if base_checkpoint_id is not None:
                self._require_checkpoint(graph, conversation_id, base_checkpoint_id)
            new_config = graph.update_state(
                self._thread_config(conversation_id, checkpoint_id=base_checkpoint_id),
                values={"messages": lc_messages},
                as_node="persist",
            )
            snapshot = graph.get_state(new_config)
            target_checkpoint_id = self._require_snapshot_checkpoint_id(snapshot)

        now = _utcnow()
        record.latest_checkpoint_id = target_checkpoint_id
        if payload.select_after_write:
            record.selected_checkpoint_id = target_checkpoint_id
        record.updated_at = now
        if payload.touch_last_activity:
            record.last_activity_at = now
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self.get_source(conversation_id)

    def patch_message(
        self,
        conversation_id: UUID,
        message_id: str,
        payload: ConversationSourcePatchRequest,
    ) -> ConversationSourceSummary | None:
        record = self._conversation_store.get_conversation(conversation_id)
        if record is None:
            return None

        target_checkpoint_id: str
        with self._open_graph() as graph:
            base_checkpoint_id = self._resolve_base_checkpoint_id(
                record.selected_checkpoint_id,
                record.latest_checkpoint_id,
                payload.base_checkpoint_id,
            )
            if base_checkpoint_id is not None:
                self._require_checkpoint(graph, conversation_id, base_checkpoint_id)

            snapshot = self._get_snapshot(
                graph,
                conversation_id=conversation_id,
                checkpoint_id=base_checkpoint_id,
            )
            existing = self._find_message(snapshot.values.get("messages", []), message_id)
            if existing is None:
                raise ConversationSourceMessageNotFoundError(
                    f"Message not found in source checkpoint: {message_id}"
                )

            patched = self._patch_langchain_message(
                existing,
                content=payload.content,
                edited_at=payload.edited_at or _utcnow(),
            )
            new_config = graph.update_state(
                self._thread_config(conversation_id, checkpoint_id=base_checkpoint_id),
                values={"messages": [patched]},
                as_node="persist",
            )
            new_snapshot = graph.get_state(new_config)
            target_checkpoint_id = self._require_snapshot_checkpoint_id(new_snapshot)

        now = _utcnow()
        record.latest_checkpoint_id = target_checkpoint_id
        if payload.select_after_write:
            record.selected_checkpoint_id = target_checkpoint_id
        record.updated_at = now
        if payload.touch_last_activity:
            record.last_activity_at = now
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self.get_source(conversation_id)

    def select_checkpoint(
        self,
        conversation_id: UUID,
        payload: ConversationSourceSelectionRequest,
    ) -> ConversationSourceSummary | None:
        record = self._conversation_store.get_conversation(conversation_id)
        if record is None:
            return None

        target_checkpoint_id = payload.checkpoint_id or record.latest_checkpoint_id
        if target_checkpoint_id is not None:
            with self._open_graph() as graph:
                self._require_checkpoint(graph, conversation_id, target_checkpoint_id)

        record.selected_checkpoint_id = target_checkpoint_id
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self.get_source(conversation_id)

    @contextmanager
    def _open_graph(self):
        settings = get_settings()
        if settings.is_postgres_database:
            from langgraph.checkpoint.postgres import PostgresSaver

            with PostgresSaver.from_conn_string(settings.langgraph_checkpoint_url) as saver:
                yield self._compile_graph(saver)
            return

        from langgraph.checkpoint.sqlite import SqliteSaver

        sqlite_path = settings.langgraph_sqlite_path
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(str(sqlite_path)) as saver:
            yield self._compile_graph(saver)

    def _compile_graph(self, checkpointer):
        builder = StateGraph(_SourceState)
        builder.add_node("persist", _persist_source_state)
        builder.add_edge(START, "persist")
        return builder.compile(checkpointer=checkpointer)

    def _thread_config(
        self,
        conversation_id: UUID,
        *,
        checkpoint_id: str | None = None,
    ) -> dict[str, dict[str, str]]:
        configurable: dict[str, str] = {"thread_id": str(conversation_id)}
        if checkpoint_id:
            configurable["checkpoint_id"] = checkpoint_id
        return {"configurable": configurable}

    def _resolve_base_checkpoint_id(
        self,
        selected_checkpoint_id: str | None,
        latest_checkpoint_id: str | None,
        override_checkpoint_id: str | None,
    ) -> str | None:
        return override_checkpoint_id or selected_checkpoint_id or latest_checkpoint_id

    def _get_snapshot(
        self,
        graph,
        *,
        conversation_id: UUID,
        checkpoint_id: str | None,
    ):
        snapshot = graph.get_state(
            self._thread_config(conversation_id, checkpoint_id=checkpoint_id)
        )
        if checkpoint_id and not self._snapshot_exists(snapshot):
            raise ConversationSourceCheckpointNotFoundError(
                f"Checkpoint not found: {checkpoint_id}"
            )
        return snapshot

    def _require_checkpoint(self, graph, conversation_id: UUID, checkpoint_id: str) -> None:
        self._get_snapshot(
            graph,
            conversation_id=conversation_id,
            checkpoint_id=checkpoint_id,
        )

    def _snapshot_exists(self, snapshot) -> bool:
        return snapshot.created_at is not None or bool(snapshot.values)

    def _snapshot_checkpoint_id(self, snapshot) -> str | None:
        return snapshot.config.get("configurable", {}).get("checkpoint_id")

    def _require_snapshot_checkpoint_id(self, snapshot) -> str:
        checkpoint_id = self._snapshot_checkpoint_id(snapshot)
        if checkpoint_id is None:
            raise RuntimeError("LangGraph snapshot did not expose a checkpoint_id")
        return checkpoint_id

    def _parent_checkpoint_id(self, snapshot) -> str | None:
        parent_config = snapshot.parent_config or {}
        return parent_config.get("configurable", {}).get("checkpoint_id")

    def _serialize_messages(
        self,
        messages: list[BaseMessage],
    ) -> list[ConversationSourceMessage]:
        return [self._serialize_message(message) for message in messages]

    def _serialize_message(self, message: BaseMessage) -> ConversationSourceMessage:
        metadata = self._chatbox_metadata(message)
        created_at = self._parse_snapshot_time(metadata.get("created_at")) or _utcnow()
        edited_at = self._parse_snapshot_time(metadata.get("edited_at"))
        return ConversationSourceMessage(
            id=str(getattr(message, "id", "")),
            role=self._message_role(message),
            content=self._message_content_as_text(message),
            created_at=created_at,
            edited_at=edited_at,
            input_tokens=metadata.get("input_tokens"),
            output_tokens=metadata.get("output_tokens"),
            model_name=metadata.get("model_name"),
            provider_name=metadata.get("provider_name"),
            attached_files=list(metadata.get("attached_files") or []),
            thinking_duration_seconds=metadata.get("thinking_duration_seconds"),
        )

    def _build_langchain_message(
        self,
        message: ConversationSourceMessage,
    ) -> BaseMessage:
        metadata = {
            "created_at": message.created_at.isoformat(),
            "edited_at": message.edited_at.isoformat() if message.edited_at else None,
            "input_tokens": message.input_tokens,
            "output_tokens": message.output_tokens,
            "model_name": message.model_name,
            "provider_name": message.provider_name,
            "attached_files": list(message.attached_files),
            "thinking_duration_seconds": message.thinking_duration_seconds,
        }
        additional_kwargs = {"chatbox": metadata}
        if message.role == "user":
            return HumanMessage(
                id=message.id,
                content=message.content,
                additional_kwargs=additional_kwargs,
            )
        if message.role == "assistant":
            return AIMessage(
                id=message.id,
                content=message.content,
                additional_kwargs=additional_kwargs,
            )
        return SystemMessage(
            id=message.id,
            content=message.content,
            additional_kwargs=additional_kwargs,
        )

    def _patch_langchain_message(
        self,
        message: BaseMessage,
        *,
        content: str,
        edited_at: datetime,
    ) -> BaseMessage:
        additional_kwargs = deepcopy(getattr(message, "additional_kwargs", {}) or {})
        chatbox = deepcopy(additional_kwargs.get("chatbox", {}) or {})
        chatbox["edited_at"] = edited_at.isoformat()
        additional_kwargs["chatbox"] = chatbox
        return message.model_copy(
            update={
                "content": content,
                "additional_kwargs": additional_kwargs,
            }
        )

    def _find_message(self, messages: list[BaseMessage], message_id: str) -> BaseMessage | None:
        for message in messages:
            if str(getattr(message, "id", "")) == message_id:
                return message
        return None

    def _chatbox_metadata(self, message: BaseMessage) -> dict[str, Any]:
        additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
        chatbox = additional_kwargs.get("chatbox")
        if isinstance(chatbox, dict):
            return chatbox
        return {}

    def _message_role(self, message: BaseMessage) -> str:
        if isinstance(message, HumanMessage):
            return "user"
        if isinstance(message, AIMessage):
            return "assistant"
        if isinstance(message, SystemMessage):
            return "system"
        message_type = getattr(message, "type", "assistant")
        return {
            "human": "user",
            "ai": "assistant",
            "system": "system",
        }.get(message_type, "assistant")

    def _message_content_as_text(self, message: BaseMessage) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return str(content)

    def _message_preview(self, message: BaseMessage) -> str:
        content = self._message_content_as_text(message).replace("\n", " ").strip()
        if len(content) <= 80:
            return content
        return f"{content[:80]}..."

    def _parse_snapshot_time(self, value: str | datetime | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
