from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from sqlmodel import Session
from typing_extensions import TypedDict

from config import get_settings
from models.conversation_source import (
    ConversationSourceCheckpointDetail,
    ConversationSourceCheckpointSummary,
    ConversationSourceMessage,
    ConversationSourcePatchRequest,
    ConversationSourceProjection,
    ConversationSourceSelectionRequest,
    ConversationSourceSummary,
    ConversationSourceThread,
    ConversationSourceThreadNode,
    ConversationSourceWriteRequest,
)
from services.conversation_store import ConversationStoreService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _SourceState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _persist_source_state(state: _SourceState) -> dict[str, object]:
    _ = state
    return {}


class ConversationSourceCheckpointNotFoundError(ValueError):
    """Raised when a requested checkpoint does not exist for the thread."""


class ConversationSourceMessageNotFoundError(ValueError):
    """Raised when a requested message does not exist in the selected checkpoint."""


@dataclass
class _SourceTreeNode:
    id: str
    parent_id: str | None
    message: ConversationSourceMessage
    children: list[str]


class _SourceTree:
    def __init__(
        self,
        *,
        conversation_id: UUID,
        nodes: dict[str, _SourceTreeNode],
        root_id: str,
        selected_child: dict[str, str],
        active_leaf_id: str,
    ) -> None:
        self.conversation_id = conversation_id
        self.nodes = nodes
        self.root_id = root_id
        self.selected_child = selected_child
        self.active_leaf_id = active_leaf_id

    @classmethod
    def empty(cls, conversation_id: UUID) -> "_SourceTree":
        return cls(
            conversation_id=conversation_id,
            nodes={},
            root_id="",
            selected_child={},
            active_leaf_id="",
        )

    @classmethod
    def from_payload(cls, payload: ConversationSourceThread) -> "_SourceTree":
        nodes = {
            node_id: _SourceTreeNode(
                id=node.id,
                parent_id=node.parent_id,
                message=deepcopy(node.message),
                children=list(node.children),
            )
            for node_id, node in payload.nodes.items()
        }
        tree = cls(
            conversation_id=payload.conversation_id,
            nodes=nodes,
            root_id=payload.root_id,
            selected_child=dict(payload.selected_child),
            active_leaf_id=payload.active_leaf_id,
        )
        tree.normalize()
        return tree

    @classmethod
    def from_projection(
        cls,
        *,
        conversation_id: UUID,
        current_messages: list[ConversationSourceMessage],
        checkpoints: list[ConversationSourceCheckpointDetail],
    ) -> "_SourceTree":
        nodes: dict[str, _SourceTreeNode] = {}
        selected_child: dict[str, str] = {}

        for checkpoint in checkpoints:
            for message in checkpoint.messages:
                nodes.setdefault(
                    message.id,
                    _SourceTreeNode(
                        id=message.id,
                        parent_id=None,
                        message=deepcopy(message),
                        children=[],
                    ),
                )

            for index, message in enumerate(checkpoint.messages):
                parent_id = None if index == 0 else checkpoint.messages[index - 1].id
                existing = nodes.get(message.id)
                if existing is None:
                    continue
                if existing.parent_id is None and parent_id is not None:
                    existing.parent_id = parent_id
                if parent_id is not None:
                    parent = nodes.get(parent_id)
                    if parent is not None and message.id not in parent.children:
                        parent.children.append(message.id)

        for index in range(len(current_messages) - 1):
            selected_child[current_messages[index].id] = current_messages[index + 1].id

        root_id = current_messages[0].id if current_messages else next(iter(nodes), "")
        active_leaf_id = current_messages[-1].id if current_messages else root_id
        tree = cls(
            conversation_id=conversation_id,
            nodes=nodes,
            root_id=root_id,
            selected_child=selected_child,
            active_leaf_id=active_leaf_id,
        )
        tree.normalize()
        return tree

    def to_payload(self) -> ConversationSourceThread:
        return ConversationSourceThread(
            conversation_id=self.conversation_id,
            nodes={
                node_id: ConversationSourceThreadNode(
                    id=node.id,
                    parent_id=node.parent_id,
                    message=deepcopy(node.message),
                    children=list(node.children),
                )
                for node_id, node in self.nodes.items()
            },
            root_id=self.root_id,
            selected_child=dict(self.selected_child),
            active_leaf_id=self.active_leaf_id,
        )

    def normalize(self) -> None:
        if not self.nodes:
            self.root_id = ""
            self.active_leaf_id = ""
            self.selected_child.clear()
            return

        if not self.root_id or self.root_id not in self.nodes:
            self.root_id = next(iter(self.nodes))

        if not self.active_leaf_id or self.active_leaf_id not in self.nodes:
            self.active_leaf_id = self.root_id

        self.selected_child = {
            parent_id: child_id
            for parent_id, child_id in self.selected_child.items()
            if parent_id in self.nodes
            and child_id in self.nodes
            and child_id in self.nodes[parent_id].children
        }

        for node in self.nodes.values():
            node.children = [
                child_id for child_id in node.children if child_id in self.nodes
            ]

        current_id = self.root_id
        while current_id:
            node = self.nodes.get(current_id)
            if node is None or not node.children:
                break
            selected = self.selected_child.get(current_id)
            next_id = (
                selected
                if selected is not None and selected in node.children
                else node.children[-1]
            )
            self.selected_child[current_id] = next_id
            current_id = next_id

        self.active_leaf_id = current_id

    def build_chain_to(self, node_id: str | None) -> list[ConversationSourceMessage]:
        if not node_id or node_id not in self.nodes:
            return []

        path: list[ConversationSourceMessage] = []
        current_id: str | None = node_id
        while current_id:
            node = self.nodes.get(current_id)
            if node is None:
                break
            path.append(deepcopy(node.message))
            current_id = node.parent_id
        path.reverse()
        return path

    def build_active_chain(self) -> list[ConversationSourceMessage]:
        return self.build_chain_to(self.resolve_selected_leaf() or None)

    def resolve_selected_leaf(self, start_id: str | None = None) -> str:
        if not self.nodes:
            return ""

        current_id = start_id or self.root_id
        if not current_id or current_id not in self.nodes:
            current_id = self.root_id

        while current_id:
            node = self.nodes.get(current_id)
            if node is None or not node.children:
                break
            selected = self.selected_child.get(current_id)
            current_id = (
                selected
                if selected is not None and selected in node.children
                else node.children[-1]
            )
        return current_id or ""

    def select_path_to_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            raise ConversationSourceMessageNotFoundError(
                f"Message not found in source tree: {node_id}"
            )

        path: list[str] = []
        current_id = node_id
        while current_id:
            path.append(current_id)
            parent_id = self.nodes[current_id].parent_id
            if parent_id is None or not parent_id:
                break
            current_id = parent_id

        for index in range(len(path) - 1, 0, -1):
            parent_id = path[index]
            child_id = path[index - 1]
            parent = self.nodes.get(parent_id)
            if parent is None or child_id not in parent.children:
                continue
            self.selected_child[parent_id] = child_id

        self.active_leaf_id = self.resolve_selected_leaf(start_id=node_id) or node_id
        self.normalize()

    def append_child_and_select(
        self,
        *,
        parent_id: str | None,
        message: ConversationSourceMessage,
    ) -> None:
        if parent_id is None or not parent_id:
            if self.nodes:
                raise ValueError("Cannot append a new root to a non-empty tree")
            self.nodes[message.id] = _SourceTreeNode(
                id=message.id,
                parent_id=None,
                message=deepcopy(message),
                children=[],
            )
            self.root_id = message.id
            self.active_leaf_id = message.id
            self.selected_child.clear()
            return

        parent = self.nodes.get(parent_id)
        if parent is None:
            raise ConversationSourceMessageNotFoundError(
                f"Parent message not found in source tree: {parent_id}"
            )

        existing = self.nodes.get(message.id)
        if existing is None:
            self.nodes[message.id] = _SourceTreeNode(
                id=message.id,
                parent_id=parent_id,
                message=deepcopy(message),
                children=[],
            )
        else:
            existing.parent_id = parent_id
            existing.message = deepcopy(message)

        if message.id not in parent.children:
            parent.children.append(message.id)

        self.select_path_to_node(parent_id)
        self.selected_child[parent_id] = message.id
        self.active_leaf_id = message.id
        self.normalize()

    def upsert_message(self, message_id: str, *, content: str, edited_at: datetime) -> None:
        node = self.nodes.get(message_id)
        if node is None:
            raise ConversationSourceMessageNotFoundError(
                f"Message not found in source tree: {message_id}"
            )
        node.message.content = content
        node.message.edited_at = edited_at

    def remove_node(self, node_id: str) -> None:
        node = self.nodes.get(node_id)
        if node is None:
            raise ConversationSourceMessageNotFoundError(
                f"Message not found in source tree: {node_id}"
            )

        parent_id = node.parent_id
        children_to_promote = list(node.children)

        if (not parent_id) and len(children_to_promote) > 1:
            current_child = self.selected_child.get(node_id)
            if current_child not in children_to_promote:
                current_child = children_to_promote[0]

            for child_id in children_to_promote:
                if child_id != current_child:
                    self._cascade_delete(child_id)

            self.root_id = current_child
            new_root = self.nodes.get(current_child)
            if new_root is not None:
                new_root.parent_id = None

            self.nodes.pop(node_id, None)
            self.selected_child.pop(node_id, None)
            self.normalize()
            return

        for child_id in children_to_promote:
            child = self.nodes.get(child_id)
            if child is not None:
                child.parent_id = parent_id

        if parent_id and parent_id in self.nodes:
            parent = self.nodes[parent_id]
            parent_children = list(parent.children)
            try:
                node_index = parent_children.index(node_id)
            except ValueError:
                node_index = -1

            if node_index >= 0:
                parent_children.pop(node_index)
                for offset, child_id in enumerate(children_to_promote):
                    parent_children.insert(node_index + offset, child_id)
            else:
                parent_children.extend(children_to_promote)
            parent.children = parent_children

            if self.selected_child.get(parent_id) == node_id:
                if children_to_promote:
                    self.selected_child[parent_id] = children_to_promote[0]
                else:
                    self.selected_child.pop(parent_id, None)
        else:
            if not children_to_promote:
                self.root_id = ""
            else:
                self.root_id = children_to_promote[0]
                new_root = self.nodes.get(self.root_id)
                if new_root is not None:
                    new_root.parent_id = None

        self.nodes.pop(node_id, None)
        self.selected_child.pop(node_id, None)
        self.normalize()

    def iter_node_ids_preorder(self) -> list[str]:
        ordered: list[str] = []

        def visit(node_id: str) -> None:
            node = self.nodes.get(node_id)
            if node is None:
                return
            ordered.append(node_id)
            for child_id in node.children:
                visit(child_id)

        if self.root_id:
            visit(self.root_id)
        return ordered

    def _cascade_delete(self, node_id: str) -> None:
        node = self.nodes.get(node_id)
        if node is None:
            return
        for child_id in list(node.children):
            self._cascade_delete(child_id)
        self.nodes.pop(node_id, None)
        self.selected_child.pop(node_id, None)


@dataclass
class _PersistedTreeState:
    namespace: str
    thread: _SourceTree
    checkpoint_by_message_id: dict[str, str]
    current_message_id: str | None
    checkpoints: dict[str, ConversationSourceCheckpointDetail]
    checkpoint_order: list[str]


class ConversationSourceService:
    """Persist and read source-thread state through backend-owned tree semantics."""

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

        state = self._load_state(conversation_id, record)
        current_checkpoint_id = checkpoint_id or self._selected_checkpoint_id(record, state)
        current_messages: list[ConversationSourceMessage] = []
        if current_checkpoint_id is not None:
            detail = state.checkpoints.get(current_checkpoint_id)
            if detail is None:
                raise ConversationSourceCheckpointNotFoundError(
                    f"Checkpoint not found: {current_checkpoint_id}"
                )
            current_messages = self._clone_source_messages(detail.messages)
        return ConversationSourceSummary(
            conversation_id=conversation_id,
            checkpoint_id=current_checkpoint_id,
            latest_checkpoint_id=record.latest_checkpoint_id,
            selected_checkpoint_id=current_checkpoint_id,
            messages=current_messages,
        )

    def list_history(
        self,
        conversation_id: UUID,
    ) -> list[ConversationSourceCheckpointSummary] | None:
        record = self._conversation_store.get_conversation(conversation_id)
        if record is None:
            return None

        state = self._load_state(conversation_id, record)
        return [
            ConversationSourceCheckpointSummary(
                checkpoint_id=detail.checkpoint_id,
                parent_checkpoint_id=detail.parent_checkpoint_id,
                source=detail.source,
                step=detail.step,
                created_at=detail.created_at,
                message_count=detail.message_count,
                last_message_id=detail.last_message_id,
                last_message_role=detail.last_message_role,
                last_message_preview=detail.last_message_preview,
            )
            for detail in self._ordered_checkpoints(state)
        ]

    def get_projection(
        self, conversation_id: UUID
    ) -> ConversationSourceProjection | None:
        record = self._conversation_store.get_conversation(conversation_id)
        if record is None:
            return None

        state = self._load_state(conversation_id, record)
        current = self.get_source(conversation_id)
        if current is None:
            return None

        return ConversationSourceProjection(
            current=current,
            checkpoints=self._ordered_checkpoints(state),
            thread=self._projection_thread_payload(state, current.messages),
            checkpoint_by_message_id=dict(state.checkpoint_by_message_id),
        )

    def append_messages(
        self,
        conversation_id: UUID,
        payload: ConversationSourceWriteRequest,
    ) -> ConversationSourceSummary | None:
        record = self._conversation_store.get_conversation(conversation_id)
        if record is None:
            return None

        state = self._load_state(conversation_id, record)
        (
            current_checkpoint_id,
            base_messages,
            parent_message_id,
        ) = self._resolve_append_base(
            conversation_id=conversation_id,
            record=record,
            state=state,
            base_message_id=payload.base_message_id,
            base_checkpoint_id=payload.base_checkpoint_id,
        )
        current_parent_id = parent_message_id
        for message in payload.messages:
            base_messages = self._clone_source_messages(base_messages)
            base_messages.append(deepcopy(message))
            checkpoint = self._append_checkpoint_detail(
                state,
                messages=base_messages,
                parent_checkpoint_id=current_checkpoint_id,
            )
            current_checkpoint_id = checkpoint.checkpoint_id
            state.thread.append_child_and_select(
                parent_id=current_parent_id,
                message=deepcopy(message),
            )
            state.checkpoint_by_message_id[message.id] = current_checkpoint_id
            current_parent_id = message.id

        if payload.select_after_write:
            state.current_message_id = current_parent_id
        self._persist_state(conversation_id, state)

        now = _utcnow()
        record.latest_checkpoint_id = current_checkpoint_id
        if payload.select_after_write:
            record.selected_checkpoint_id = current_checkpoint_id
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

        state = self._load_state(conversation_id, record)
        if message_id not in state.thread.nodes:
            raise ConversationSourceMessageNotFoundError(
                f"Message not found in source tree: {message_id}"
            )

        edited_at = payload.edited_at or _utcnow()
        base_checkpoint_id = (
            payload.base_checkpoint_id or self._selected_checkpoint_id(record, state)
        )
        if base_checkpoint_id is None:
            raise ConversationSourceCheckpointNotFoundError(
                f"Checkpoint not found: {payload.base_checkpoint_id or ''}"
            )
        current_checkpoint = state.checkpoints.get(base_checkpoint_id)
        if current_checkpoint is None:
            raise ConversationSourceCheckpointNotFoundError(
                f"Checkpoint not found: {base_checkpoint_id}"
            )

        visible_messages = self._clone_source_messages(current_checkpoint.messages)
        target_index = next(
            (index for index, item in enumerate(visible_messages) if item.id == message_id),
            -1,
        )
        if target_index < 0:
            raise ConversationSourceMessageNotFoundError(
                f"Message not found in selected checkpoint: {message_id}"
            )

        visible_messages[target_index].content = payload.content
        visible_messages[target_index].edited_at = edited_at
        state.thread.upsert_message(
            message_id,
            content=payload.content,
            edited_at=edited_at,
        )

        parent_checkpoint_id = self._ensure_checkpoint_for_messages(
            state,
            visible_messages[:target_index],
        )
        current_checkpoint_id: str | None = None
        for index in range(target_index, len(visible_messages)):
            checkpoint = self._append_checkpoint_detail(
                state,
                messages=visible_messages[: index + 1],
                parent_checkpoint_id=parent_checkpoint_id,
            )
            parent_checkpoint_id = checkpoint.checkpoint_id
            current_checkpoint_id = checkpoint.checkpoint_id
            state.checkpoint_by_message_id[visible_messages[index].id] = (
                checkpoint.checkpoint_id
            )

        if payload.select_after_write and visible_messages:
            selected_message_id = visible_messages[-1].id
            if selected_message_id in state.thread.nodes:
                state.thread.select_path_to_node(selected_message_id)
            state.current_message_id = selected_message_id
        self._persist_state(conversation_id, state)

        now = _utcnow()
        record.latest_checkpoint_id = current_checkpoint_id
        if payload.select_after_write:
            record.selected_checkpoint_id = current_checkpoint_id
        record.updated_at = now
        if payload.touch_last_activity:
            record.last_activity_at = now
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self.get_source(conversation_id)

    def delete_message(
        self,
        conversation_id: UUID,
        message_id: str,
    ) -> ConversationSourceSummary | None:
        record = self._conversation_store.get_conversation(conversation_id)
        if record is None:
            return None

        state = self._load_state(conversation_id, record)
        previous_node_ids = set(state.thread.nodes.keys())
        state.thread.remove_node(message_id)
        removed_message_ids = previous_node_ids.difference(state.thread.nodes.keys())
        if state.current_message_id not in state.thread.nodes:
            state.current_message_id = state.thread.resolve_selected_leaf() or None

        self._prune_checkpoints(state, removed_message_ids)
        state.checkpoint_by_message_id = self._rebuild_current_checkpoint_bindings(state)
        self._persist_state(conversation_id, state)

        now = _utcnow()
        record.selected_checkpoint_id = (
            state.checkpoint_by_message_id.get(state.current_message_id)
            if state.current_message_id
            else None
        )
        record.latest_checkpoint_id = state.checkpoint_by_message_id.get(
            state.thread.resolve_selected_leaf()
        )
        record.updated_at = now
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

        state = self._load_state(conversation_id, record)
        target_checkpoint_id: str | None = None

        if payload.message_id is not None:
            if payload.message_id not in state.thread.nodes:
                raise ConversationSourceMessageNotFoundError(
                    f"Message not found in source tree: {payload.message_id}"
                )
            state.thread.select_path_to_node(payload.message_id)
            target_checkpoint_id = self._checkpoint_id_for_message(
                state,
                payload.message_id,
            )
            if target_checkpoint_id is None:
                raise ConversationSourceCheckpointNotFoundError(
                    f"Checkpoint not found for message: {payload.message_id}"
                )
            target_message_id = payload.message_id
        else:
            target_checkpoint_id = payload.checkpoint_id or record.latest_checkpoint_id
            if target_checkpoint_id is not None:
                checkpoint = state.checkpoints.get(target_checkpoint_id)
                if checkpoint is None:
                    raise ConversationSourceCheckpointNotFoundError(
                        f"Checkpoint not found: {target_checkpoint_id}"
                    )
                target_message_id = checkpoint.last_message_id
                if target_message_id and target_message_id in state.thread.nodes:
                    state.thread.select_path_to_node(target_message_id)
            else:
                target_message_id = None

        state.current_message_id = target_message_id
        self._persist_state(conversation_id, state)

        record.selected_checkpoint_id = target_checkpoint_id
        record.updated_at = _utcnow()
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self.get_source(conversation_id)

    def clear_source(self, conversation_id: UUID) -> ConversationSourceSummary | None:
        record = self._conversation_store.get_conversation(conversation_id)
        if record is None:
            return None

        self._conversation_store.delete_source_graph(conversation_id)
        self._conversation_store.set_hidden_source_message_ids(conversation_id, [])
        record.selected_checkpoint_id = None
        record.latest_checkpoint_id = None
        record.updated_at = _utcnow()
        record.last_activity_at = record.updated_at
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return ConversationSourceSummary(
            conversation_id=conversation_id,
            checkpoint_id=None,
            latest_checkpoint_id=None,
            selected_checkpoint_id=None,
            messages=[],
        )

    def _load_state(
        self,
        conversation_id: UUID,
        record,
    ) -> _PersistedTreeState:
        stored = self._conversation_store.get_source_graph(conversation_id)
        if stored is not None and stored.thread_state:
            payload = dict(stored.thread_state or {})
            if "thread" in payload:
                return self._state_from_stored_payload(
                    conversation_id=conversation_id,
                    stored=stored,
                    payload=payload,
                )

            try:
                thread_payload = ConversationSourceThread.model_validate(payload)
            except Exception:
                thread_payload = None

            if thread_payload is not None:
                thread = _SourceTree.from_payload(thread_payload)
                checkpoints, checkpoint_order = self._load_legacy_checkpoints(
                    conversation_id=conversation_id,
                    namespace=stored.namespace,
                )
                state = _PersistedTreeState(
                    namespace=stored.namespace,
                    thread=thread,
                    checkpoint_by_message_id=dict(stored.checkpoint_by_message_id or {}),
                    current_message_id=self._normalize_current_message_id(
                        thread,
                        stored.current_message_id,
                    ),
                    checkpoints=checkpoints,
                    checkpoint_order=checkpoint_order,
                )
                if not state.checkpoint_by_message_id and state.thread.nodes:
                    state.checkpoint_by_message_id = self._checkpoint_bindings_from_details(
                        self._ordered_checkpoints(state)
                    )
                if not state.checkpoint_by_message_id and state.thread.nodes:
                    state.checkpoint_by_message_id = self._rebuild_current_checkpoint_bindings(
                        state
                    )
                self._persist_state(conversation_id, state)
                return state

        selected_checkpoint_id = record.selected_checkpoint_id or record.latest_checkpoint_id
        if selected_checkpoint_id is None:
            return _PersistedTreeState(
                namespace="",
                thread=_SourceTree.empty(conversation_id),
                checkpoint_by_message_id={},
                current_message_id=None,
                checkpoints={},
                checkpoint_order=[],
            )

        with self._open_graph() as graph:
            current_snapshot = self._get_snapshot(
                graph,
                conversation_id=conversation_id,
                namespace="",
                checkpoint_id=selected_checkpoint_id,
            )
            history = list(graph.get_state_history(self._thread_config(conversation_id)))

        current_messages = self._serialize_messages(current_snapshot.values.get("messages", []))
        checkpoints = self._checkpoint_details_from_history(history)
        thread = _SourceTree.from_projection(
            conversation_id=conversation_id,
            current_messages=current_messages,
            checkpoints=checkpoints,
        )

        state = _PersistedTreeState(
            namespace="",
            thread=thread,
            checkpoint_by_message_id=self._checkpoint_bindings_from_details(
                checkpoints
            ),
            current_message_id=current_messages[-1].id if current_messages else None,
            checkpoints={
                item.checkpoint_id: item for item in checkpoints if item.checkpoint_id
            },
            checkpoint_order=[
                item.checkpoint_id for item in checkpoints if item.checkpoint_id
            ],
        )
        self._persist_state(conversation_id, state)
        return state

    def _persist_state(self, conversation_id: UUID, state: _PersistedTreeState) -> None:
        self._conversation_store.upsert_source_graph(
            conversation_id,
            namespace=state.namespace,
            thread_state={
                "version": 2,
                "thread": state.thread.to_payload().model_dump(mode="json"),
                "checkpoints": [
                    state.checkpoints[checkpoint_id].model_dump(mode="json")
                    for checkpoint_id in state.checkpoint_order
                    if checkpoint_id in state.checkpoints
                ],
                "checkpoint_order": list(state.checkpoint_order),
            },
            checkpoint_by_message_id=state.checkpoint_by_message_id,
            current_message_id=state.current_message_id,
        )

    def _state_from_stored_payload(
        self,
        *,
        conversation_id: UUID,
        stored,
        payload: dict[str, object],
    ) -> _PersistedTreeState:
        thread_payload = ConversationSourceThread.model_validate(payload.get("thread") or {})
        checkpoints_raw = payload.get("checkpoints") or []
        checkpoints_list = [
            ConversationSourceCheckpointDetail.model_validate(item)
            for item in checkpoints_raw
            if isinstance(item, dict)
        ]
        checkpoints = {
            item.checkpoint_id: item for item in checkpoints_list if item.checkpoint_id
        }
        checkpoint_order = [
            checkpoint_id
            for checkpoint_id in payload.get("checkpoint_order") or []
            if isinstance(checkpoint_id, str) and checkpoint_id in checkpoints
        ]
        if not checkpoint_order:
            checkpoint_order = [
                item.checkpoint_id for item in checkpoints_list if item.checkpoint_id
            ]

        thread = _SourceTree.from_payload(thread_payload)
        state = _PersistedTreeState(
            namespace=stored.namespace,
            thread=thread,
            checkpoint_by_message_id=dict(stored.checkpoint_by_message_id or {}),
            current_message_id=self._normalize_current_message_id(
                thread,
                stored.current_message_id,
            ),
            checkpoints=checkpoints,
            checkpoint_order=checkpoint_order,
        )
        if not state.checkpoint_by_message_id and state.thread.nodes:
            state.checkpoint_by_message_id = self._checkpoint_bindings_from_details(
                self._ordered_checkpoints(state)
            )
        if not state.checkpoint_by_message_id and state.thread.nodes:
            state.checkpoint_by_message_id = self._rebuild_current_checkpoint_bindings(
                state
            )
        return state

    def _resolve_append_base(
        self,
        *,
        conversation_id: UUID,
        record,
        state: _PersistedTreeState,
        base_message_id: str | None,
        base_checkpoint_id: str | None,
    ) -> tuple[str | None, list[ConversationSourceMessage], str | None]:
        _ = conversation_id
        if base_message_id is not None:
            if base_message_id and base_message_id not in state.thread.nodes:
                raise ConversationSourceMessageNotFoundError(
                    f"Message not found in source tree: {base_message_id}"
                )
            if not base_message_id:
                return None, [], None
            checkpoint_id = self._checkpoint_id_for_message(state, base_message_id)
            if checkpoint_id is None:
                return None, state.thread.build_chain_to(base_message_id), base_message_id
            checkpoint = state.checkpoints.get(checkpoint_id)
            if checkpoint is None:
                raise ConversationSourceCheckpointNotFoundError(
                    f"Checkpoint not found: {checkpoint_id}"
                )
            return checkpoint_id, checkpoint.messages, base_message_id

        if base_checkpoint_id is not None:
            if base_checkpoint_id == "":
                return None, [], None
            checkpoint = state.checkpoints.get(base_checkpoint_id)
            if checkpoint is None:
                raise ConversationSourceCheckpointNotFoundError(
                    f"Checkpoint not found: {base_checkpoint_id}"
                )
            return base_checkpoint_id, checkpoint.messages, checkpoint.last_message_id

        selected_checkpoint_id = self._selected_checkpoint_id(record, state)
        if selected_checkpoint_id is None:
            return None, [], None
        checkpoint = state.checkpoints.get(selected_checkpoint_id)
        if checkpoint is None:
            raise ConversationSourceCheckpointNotFoundError(
                f"Checkpoint not found: {selected_checkpoint_id}"
            )
        return selected_checkpoint_id, checkpoint.messages, checkpoint.last_message_id

    def _selected_checkpoint_id(self, record, state: _PersistedTreeState) -> str | None:
        if record.selected_checkpoint_id:
            return record.selected_checkpoint_id
        if record.latest_checkpoint_id:
            return record.latest_checkpoint_id
        if state.current_message_id:
            return state.checkpoint_by_message_id.get(state.current_message_id)
        return None

    def _ordered_checkpoints(
        self,
        state: _PersistedTreeState,
    ) -> list[ConversationSourceCheckpointDetail]:
        return [
            state.checkpoints[checkpoint_id]
            for checkpoint_id in state.checkpoint_order
            if checkpoint_id in state.checkpoints
        ]

    def _projection_thread_payload(
        self,
        state: _PersistedTreeState,
        current_messages: list[ConversationSourceMessage],
    ) -> ConversationSourceThread:
        projected = _SourceTree.from_payload(state.thread.to_payload())
        for message in current_messages:
            node = projected.nodes.get(message.id)
            if node is not None:
                node.message = deepcopy(message)

        if current_messages:
            projected.selected_child.clear()
            for index in range(len(current_messages) - 1):
                parent_id = current_messages[index].id
                child_id = current_messages[index + 1].id
                parent = projected.nodes.get(parent_id)
                if parent is not None and child_id in parent.children:
                    projected.selected_child[parent_id] = child_id
            projected.active_leaf_id = current_messages[-1].id
        projected.normalize()
        return projected.to_payload()

    def _checkpoint_id_for_message(
        self,
        state: _PersistedTreeState,
        message_id: str,
    ) -> str | None:
        checkpoint_id = state.checkpoint_by_message_id.get(message_id)
        if checkpoint_id and checkpoint_id in state.checkpoints:
            return checkpoint_id
        for checkpoint in self._ordered_checkpoints(state):
            if checkpoint.last_message_id == message_id:
                return checkpoint.checkpoint_id
        return None

    def _append_checkpoint_detail(
        self,
        state: _PersistedTreeState,
        *,
        messages: list[ConversationSourceMessage],
        parent_checkpoint_id: str | None,
    ) -> ConversationSourceCheckpointDetail:
        checkpoint_id = str(uuid4())
        copied_messages = self._clone_source_messages(messages)
        last_message = copied_messages[-1] if copied_messages else None
        detail = ConversationSourceCheckpointDetail(
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            created_at=_utcnow(),
            message_count=len(copied_messages),
            last_message_id=last_message.id if last_message is not None else None,
            last_message_role=last_message.role if last_message is not None else None,
            last_message_preview=(
                self._message_preview_from_source(last_message)
                if last_message is not None
                else None
            ),
            messages=copied_messages,
        )
        state.checkpoints[checkpoint_id] = detail
        if checkpoint_id in state.checkpoint_order:
            state.checkpoint_order.remove(checkpoint_id)
        state.checkpoint_order.insert(0, checkpoint_id)
        return detail

    def _ensure_checkpoint_for_messages(
        self,
        state: _PersistedTreeState,
        messages: list[ConversationSourceMessage],
    ) -> str | None:
        if not messages:
            return None
        target = self._clone_source_messages(messages)
        for checkpoint in self._ordered_checkpoints(state):
            if checkpoint.message_count != len(target):
                continue
            if checkpoint.messages == target:
                return checkpoint.checkpoint_id
        parent_checkpoint_id = self._ensure_checkpoint_for_messages(state, target[:-1])
        checkpoint = self._append_checkpoint_detail(
            state,
            messages=target,
            parent_checkpoint_id=parent_checkpoint_id,
        )
        return checkpoint.checkpoint_id

    def _prune_checkpoints(
        self,
        state: _PersistedTreeState,
        removed_message_ids: set[str],
    ) -> None:
        if not removed_message_ids:
            return
        removed_checkpoint_ids = {
            checkpoint_id
            for checkpoint_id, checkpoint in state.checkpoints.items()
            if any(message.id in removed_message_ids for message in checkpoint.messages)
        }
        for checkpoint_id in removed_checkpoint_ids:
            state.checkpoints.pop(checkpoint_id, None)
        state.checkpoint_order = [
            checkpoint_id
            for checkpoint_id in state.checkpoint_order
            if checkpoint_id not in removed_checkpoint_ids
        ]
        state.checkpoint_by_message_id = {
            message_id: checkpoint_id
            for message_id, checkpoint_id in state.checkpoint_by_message_id.items()
            if checkpoint_id not in removed_checkpoint_ids
            and message_id not in removed_message_ids
        }

    def _rebuild_current_checkpoint_bindings(
        self,
        state: _PersistedTreeState,
    ) -> dict[str, str]:
        checkpoint_by_message_id: dict[str, str] = {}
        if not state.thread.nodes:
            return checkpoint_by_message_id

        for node_id in state.thread.iter_node_ids_preorder():
            checkpoint_id = self._ensure_checkpoint_for_messages(
                state,
                state.thread.build_chain_to(node_id),
            )
            if checkpoint_id is not None:
                checkpoint_by_message_id[node_id] = checkpoint_id
        return checkpoint_by_message_id

    def _load_legacy_checkpoints(
        self,
        *,
        conversation_id: UUID,
        namespace: str,
    ) -> tuple[dict[str, ConversationSourceCheckpointDetail], list[str]]:
        with self._open_graph() as graph:
            history = list(
                graph.get_state_history(
                    self._thread_config(conversation_id, namespace=namespace)
                )
            )
        checkpoints_list = self._checkpoint_details_from_history(history)
        checkpoints = {
            item.checkpoint_id: item for item in checkpoints_list if item.checkpoint_id
        }
        checkpoint_order = [
            item.checkpoint_id for item in checkpoints_list if item.checkpoint_id
        ]
        return checkpoints, checkpoint_order

    def _checkpoint_bindings_from_details(
        self,
        checkpoints: list[ConversationSourceCheckpointDetail],
    ) -> dict[str, str]:
        checkpoint_by_message_id: dict[str, str] = {}
        for checkpoint in reversed(checkpoints):
            if checkpoint.last_message_id is None:
                continue
            checkpoint_by_message_id[checkpoint.last_message_id] = (
                checkpoint.checkpoint_id
            )
        return checkpoint_by_message_id

    def _normalize_current_message_id(
        self,
        thread: _SourceTree,
        current_message_id: str | None,
    ) -> str | None:
        if current_message_id and current_message_id in thread.nodes:
            return current_message_id
        return thread.resolve_selected_leaf() or None

    def _clone_source_messages(
        self,
        messages: list[ConversationSourceMessage],
    ) -> list[ConversationSourceMessage]:
        return [deepcopy(message) for message in messages]

    @contextmanager
    def _open_graph(self):
        settings = get_settings()
        if settings.is_postgres_database:
            from langgraph.checkpoint.postgres import PostgresSaver

            with PostgresSaver.from_conn_string(
                settings.langgraph_checkpoint_url
            ) as saver:
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
        namespace: str = "",
        checkpoint_id: str | None = None,
    ) -> dict[str, dict[str, str]]:
        configurable: dict[str, str] = {
            "thread_id": self._thread_id(conversation_id, namespace=namespace),
            "checkpoint_ns": "",
        }
        if checkpoint_id:
            configurable["checkpoint_id"] = checkpoint_id
        return {"configurable": configurable}

    def _thread_id(self, conversation_id: UUID, *, namespace: str = "") -> str:
        if not namespace:
            return str(conversation_id)
        return f"{conversation_id}:{namespace}"

    def _write_single_message(
        self,
        graph,
        *,
        conversation_id: UUID,
        namespace: str,
        base_checkpoint_id: str | None,
        message: ConversationSourceMessage,
    ) -> str:
        new_config = graph.update_state(
            self._thread_config(
                conversation_id,
                namespace=namespace,
                checkpoint_id=base_checkpoint_id,
            ),
            values={"messages": [self._build_langchain_message(message)]},
            as_node="persist",
        )
        snapshot = graph.get_state(new_config)
        return self._require_snapshot_checkpoint_id(snapshot)

    def _get_snapshot(
        self,
        graph,
        *,
        conversation_id: UUID,
        namespace: str,
        checkpoint_id: str | None,
    ):
        snapshot = graph.get_state(
            self._thread_config(
                conversation_id,
                namespace=namespace,
                checkpoint_id=checkpoint_id,
            )
        )
        if checkpoint_id and not self._snapshot_exists(snapshot):
            raise ConversationSourceCheckpointNotFoundError(
                f"Checkpoint not found: {checkpoint_id}"
            )
        return snapshot

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

    def _checkpoint_details_from_history(
        self,
        history: list[Any],
    ) -> list[ConversationSourceCheckpointDetail]:
        checkpoints: list[ConversationSourceCheckpointDetail] = []
        for snapshot in history:
            checkpoint_id = self._snapshot_checkpoint_id(snapshot)
            if checkpoint_id is None:
                continue
            messages = self._serialize_messages(snapshot.values.get("messages", []))
            last_message = messages[-1] if messages else None
            checkpoints.append(
                ConversationSourceCheckpointDetail(
                    checkpoint_id=checkpoint_id,
                    parent_checkpoint_id=self._parent_checkpoint_id(snapshot),
                    source=(snapshot.metadata or {}).get("source"),
                    step=(snapshot.metadata or {}).get("step"),
                    created_at=self._parse_snapshot_time(snapshot.created_at),
                    message_count=len(messages),
                    last_message_id=last_message.id if last_message is not None else None,
                    last_message_role=last_message.role if last_message is not None else None,
                    last_message_preview=(
                        self._message_preview_from_source(last_message)
                        if last_message is not None
                        else None
                    ),
                    messages=messages,
                )
            )
        return checkpoints

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
            tool_call_records=list(metadata.get("tool_call_records") or []),
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
            "tool_call_records": list(message.tool_call_records),
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

    def _message_preview_from_source(self, message: ConversationSourceMessage) -> str:
        content = message.content.replace("\n", " ").strip()
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
