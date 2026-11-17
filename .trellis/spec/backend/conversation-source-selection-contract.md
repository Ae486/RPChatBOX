# Conversation Source Selection Contract

## Scenario: Message-id selection resolves to the active branch leaf

### 1. Scope / Trigger

- Trigger: backend conversation source selection APIs that switch visible chat branches.
- Applies to: `backend/services/conversation_source.py` and `backend/api/conversation_source.py`.
- The frontend may select a branch by clicking an intermediate message, such as an assistant variant directly under a user message. The backend must display the complete selected branch, not only the checkpoint whose last message is the clicked node.

### 2. Signatures

- `PUT /api/conversations/{conversation_id}/source/selection`
- Request model: `ConversationSourceSelectionRequest`
  - `checkpoint_id: str | None`
  - `message_id: str | None`
- Service entrypoint:
  - `ConversationSourceService.select_checkpoint(conversation_id, payload)`

### 3. Contracts

- If `message_id` is provided:
  - Validate that the message exists in `state.thread.nodes`.
  - Call `state.thread.select_path_to_node(message_id)` so tree selection follows the clicked branch.
  - Resolve the selected active leaf after path selection.
  - Persist `state.current_message_id` as that leaf id.
  - Persist `record.selected_checkpoint_id` as the checkpoint for that leaf id.
  - Return `ConversationSourceSummary.messages` for the full selected branch checkpoint.
- If `checkpoint_id` is provided:
  - Preserve exact checkpoint selection semantics.
  - Resolve the checkpoint last message into tree selection when possible.

### 4. Validation & Error Matrix

| Condition | Result |
|---|---|
| `message_id` is absent and `checkpoint_id` is absent | Select latest checkpoint when present |
| `message_id` is not in the source tree | `ConversationSourceMessageNotFoundError` -> 404 `message_not_found` |
| selected branch leaf has no checkpoint binding | `ConversationSourceCheckpointNotFoundError` -> 404 `checkpoint_not_found` |
| `checkpoint_id` does not exist | `ConversationSourceCheckpointNotFoundError` -> 404 `checkpoint_not_found` |

### 5. Good/Base/Bad Cases

- Good: selecting `assistant-a` under `user-1` where the branch continues through `user-a2 -> assistant-a2` returns `user-1, assistant-a, user-a2, assistant-a2`.
- Base: selecting a terminal assistant message returns the same chain as its checkpoint.
- Bad: selecting `assistant-a` returns only `user-1, assistant-a` while downstream messages on that selected branch are hidden.

### 6. Tests Required

- API regression test must create a branched conversation where the selected assistant variant has descendants.
- Assert `PUT /source/selection` with `message_id=<intermediate assistant>` returns `selected_checkpoint_id` for the branch leaf, not the clicked message.
- Assert both immediate response and subsequent `GET /source` expose the full selected message id chain.

### 7. Wrong vs Correct

#### Wrong

```python
state.thread.select_path_to_node(payload.message_id)
target_checkpoint_id = self._checkpoint_id_for_message(state, payload.message_id)
state.current_message_id = payload.message_id
```

This chooses the clicked node checkpoint and truncates visible messages to that prefix.

#### Correct

```python
state.thread.select_path_to_node(payload.message_id)
target_message_id = state.thread.active_leaf_id or payload.message_id
target_checkpoint_id = self._checkpoint_id_for_message(state, target_message_id)
state.current_message_id = target_message_id
```

This keeps the clicked branch selected and returns the checkpoint that represents the complete active branch.
