# Backend Migration Bug Investigation

Date: 2026-04-09
Scope: investigate reported backend-migration/runtime bugs by reading code first, document each confirmed finding before any fix.
Status: in progress

## Issue 1. UI only refreshes after scrolling away and back

### Reported symptoms

- Manual abort does not immediately show the `Request was aborted` block.
- Assistant token footer does not immediately refresh after finalize.
- Message edit `save` still shows the old content until the user scrolls away and back.

### Confirmed conclusion

The primary cause is in the Flutter chat list update path, not in backend persistence caching.

Backend mode currently routes many same-message-id mutations through full-list `setMessages()` sync, but the patched `flutter_chat_ui` stack only reliably updates visible rows immediately when it receives `ChatOperation.update`. When the change comes from `setMessages()` with the same message id, the row state can keep rendering the old cached `Message` object until that row leaves the viewport and gets rebuilt.

### Evidence chain

#### 1. Backend mode uses full-list sync for same-id mutations

Visible-chain sync always goes through `setMessages()`:

- `lib/widgets/conversation_view_v2/scroll_and_highlight.dart:13`
  - `_syncConversationToChatController()` builds the active chain and calls `_chatController.setMessages(msgs, animated: false)` (line 29).

Backend-mode edit `save` does not call `_chatController.updateMessage()`:

- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:119`
  - user-message backend `save` calls `_backendConversationSourceService.patchMessage(...)`
- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:125`
  - then calls `_loadBackendConversationState(autoFollow: false)`
- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:371`
  - assistant-message backend `save` also calls `_backendConversationSourceService.patchMessage(...)`
- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:377`
  - then calls `_loadBackendConversationState(autoFollow: false)`

Backend-mode stream finalize also uses snapshot/projection sync, not per-message update:

- `lib/widgets/conversation_view_v2/streaming.dart:1092`
  - finalize appends the assistant message to backend
- `lib/widgets/conversation_view_v2/streaming.dart:1096`
  - then calls `_applyBackendSourceSnapshot(snapshot, autoFollow: false)`
- `lib/widgets/conversation_view_v2/streaming.dart:1097`
  - then refreshes projection in background
- `lib/widgets/conversation_view_v2.dart:574`
  - `_applyBackendSourceSnapshot()` ends by calling `_syncConversationToChatController(...)`

By contrast, local mode explicitly uses `_chatController.updateMessage()` for same-id replacements:

- `lib/widgets/conversation_view_v2/streaming.dart:1127`
  - local finalize tries `await _chatController.updateMessage(placeholder, converted)`
- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:149`
  - local user edit `save` uses `await _chatController.updateMessage(message, converted)`
- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:401`
  - local assistant edit `save` also uses `await _chatController.updateMessage(message, converted)`

#### 2. `flutter_chat_ui` only updates visible row state immediately on `ChatOperation.update`

`ChatMessageInternal` stores its own `_updatedMessage` state:

- `packages/flutter_chat_ui/lib/src/chat_message/chat_message_internal.dart:60`
  - `_updatedMessage = widget.message` is only initialized in `initState()`

It listens to controller operations and updates state only for `ChatOperationType.update`:

- `packages/flutter_chat_ui/lib/src/chat_message/chat_message_internal.dart:66`
  - subscribes to `operationsStream`
- `packages/flutter_chat_ui/lib/src/chat_message/chat_message_internal.dart:68`
  - handles `ChatOperationType.update`
- `packages/flutter_chat_ui/lib/src/chat_message/chat_message_internal.dart:78`
  - `setState(() { _updatedMessage = event.message!; })`

It has no `didUpdateWidget()` to refresh `_updatedMessage` from a new widget payload when the controller performs a list-level replacement instead of an update event.

#### 3. `setMessages()` does not emit `update`; it emits `set`, which is diffed into remove/insert/change at the animated-list layer

- `C:/Users/55473/AppData/Local/Pub/Cache/hosted/pub.dev/flutter_chat_core-2.9.0/lib/src/chat_controller/in_memory_chat_controller.dart:158`
  - `setMessages()` replaces `_messages` and emits `ChatOperation.set(...)`

- `packages/flutter_chat_ui/lib/src/chat_animated_list/chat_animated_list.dart:1386`
  - `ChatOperationType.set` is diffed with `calculateDiff(...)`
- `packages/flutter_chat_ui/lib/src/chat_animated_list/chat_animated_list.dart:1335`
  - diff `change` is handled by `_onChanged(...)` (via `_onDiffUpdate`)
- `packages/flutter_chat_ui/lib/src/chat_animated_list/chat_animated_list.dart:1265`
  - `_onChanged(...)` is implemented as `_onRemoved(...)` + `_onInserted(...)`

Rows are keyed only by message id:

- `packages/flutter_chat_ui/lib/src/chat.dart:184`
  - `ChatMessageInternal(key: ValueKey(message.id), ...)`

This creates the failure mode:

1. backend mode changes a message but keeps the same message id
2. app syncs through `setMessages()`
3. visible row does not receive `ChatOperation.update`
4. row state can keep the old `_updatedMessage`
5. once the row scrolls off-screen and is recreated, the newest widget payload is finally used

That directly matches the observed “scroll away and come back, then it renders correctly”.

### Why this explains the three reported symptoms

#### A. Abort error block is delayed

Manual abort finalizes the active assistant placeholder into a persisted assistant message with the same id:

- `lib/widgets/conversation_view_v2/streaming.dart:1216`
  - `_stopStreaming()` calls `_finalizeStreamingMessage(...)`
- `lib/widgets/conversation_view_v2/streaming.dart:1075`
  - finalize computes the final content
- `lib/widgets/conversation_view_v2/streaming.dart:1096`
  - backend mode applies snapshot sync, which ends in `setMessages()`

The message id stays the same as the placeholder id, but content and metadata change.

#### B. Token footer is delayed

Token footer is rendered from message metadata:

- `lib/widgets/conversation_view_v2/tokens_and_ids.dart:36`
  - `_buildTokenFooter()` reads `inputTokens` / `outputTokens` from `message.metadata`

Finalize computes new token counts on the same assistant message id:

- `lib/widgets/conversation_view_v2/streaming.dart:1075`
  - `final outputTokens = TokenCounter.estimateTokens(finalContent);`

If the visible row does not refresh immediately, the footer also stays stale until the row is rebuilt.

#### C. Edit `save` still shows old content

Backend edit `save` patches the existing message id in place:

- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:119`
- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:371`

The UI refresh path is still projection reload + `setMessages()`, not `updateMessage()`, so the same row-state problem applies.

### Other flows affected by the same root cause

Any backend-mode flow that mutates an existing message id and then relies on `_syncConversationToChatController()` is exposed to the same delayed-repaint behavior:

- assistant/user message `save`
- stream finalize success
- stream finalize with error tag
- image persistence patch after finalize
  - `lib/widgets/conversation_view_v2.dart:458`
  - `lib/widgets/conversation_view_v2.dart:465`
- sweep-time markdown image patch
  - `lib/widgets/conversation_view_v2.dart:420`
  - `lib/widgets/conversation_view_v2.dart:428`

### Non-conclusion

This finding does not prove there are no secondary issues in backend projection or source-thread logic.

It does prove that issue 1 has a frontend rendering-layer bug that is sufficient on its own to explain the observed “not updated until scroll recycle” behavior.

## Next issues

- Issue 2. Message tree / regenerate / delete semantics
- Issue 3. Error does not terminate UI loading state
- Issue 5. Normal chat mode unexpectedly retries

## Issue 2. Message tree / regenerate / delete semantics

### Reported symptoms

- A. Regenerate should create sibling assistant variants under the same user message, but actual behavior becomes a linear chain like `U1 -> A1(old) -> A1(new) -> A1(newnew)`.
- B. Delete does not work as expected.
- C. Some replies appear split into multiple assistant sections, and clicking regenerate can surface truncated old content instead of behaving like a clean re-request.

### Confirmed conclusion

This is not just a small bug in one handler. The current backend-mode message-tree behavior is a partial migration with two concrete semantic mismatches:

1. backend source persistence is currently a LangGraph checkpointed linear-message state, and Flutter still rebuilds a pseudo-tree locally from checkpoint history
2. backend-mode regenerate/delete paths rely on a "rebuild prefix from empty base" assumption that is false for the current `LangGraph + add_messages` implementation

The direct consequence is:

- regenerate in backend mode is currently wired in a way that can append a new assistant after the previous assistant instead of forking under the user message
- delete in backend mode is not actually a migrated node-delete operation; it is a prefix rollback shim, and that shim is itself currently using the wrong LangGraph write semantics

### Current backend implementation: what it actually does

#### 1. The backend does not store a native tree; it stores checkpointed message lists

Current backend source state is only:

- `backend/services/conversation_source.py:34`
  - `_SourceState.messages: Annotated[list[BaseMessage], add_messages]`

All writes go through `graph.update_state(...)`:

- `backend/services/conversation_source.py:196`
  - `append_messages()` writes `values={"messages": lc_messages}`
- `backend/services/conversation_source.py:252`
  - `patch_message()` writes `values={"messages": [patched]}`

The backend projection API returns:

- `current`: selected checkpoint-visible linear message list
- `checkpoints`: all checkpoint-visible linear message lists

It does not return a backend-native branch/read model:

- `backend/models/conversation_source.py:80`
- `backend/services/conversation_source.py:128`

#### 2. Flutter still reconstructs the tree locally from checkpoint history

Backend mode rebuilds `ConversationThread` on the Flutter side:

- `lib/services/backend_conversation_source_service.dart:218`
  - `_buildProjection(...)` iterates every checkpoint and reconstructs parent/child links by message order inside each checkpoint
- `lib/widgets/conversation_view_v2.dart:561`
  - `_applyBackendProjection(...)` stores `projection.thread`
- `lib/widgets/conversation_view_v2/scroll_and_highlight.dart:14`
  - chat rendering still uses `thread.buildActiveChain()`

So current backend mode is not "backend owns tree semantics". It is "backend owns checkpoints, Flutter still infers tree semantics from checkpoint lists".

### Old Flutter tree semantics: the baseline being compared against

#### 1. Local regenerate really creates assistant siblings under the same user

Original local-mode regenerate path:

- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:778`
  - local regenerate calls `_startAssistantResponse(parentUserMessageId: target.id, ...)`
- `lib/widgets/conversation_view_v2/streaming.dart:133`
  - local path pre-creates a placeholder assistant variant under that user
- `lib/models/conversation_thread.dart:450`
  - `appendAssistantVariantUnderUser(...)`
- `lib/models/conversation_thread.dart:367`
  - `appendAssistantChildUnderUserAndSelect(...)` inserts the assistant as a child of the user node and updates `selectedChild[userId]`

That is why old local behavior is:

- same user node stays in place
- each regenerated assistant is a sibling variant under that user
- branch switcher under the user can cycle those siblings

#### 2. Local delete is true tree deletion, not prefix rollback

Original local delete path:

- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:547`
  - local delete calls `thread.removeNode(message.id)`
- `lib/models/conversation_thread.dart:216`
  - `removeNode(...)` promotes children to the parent, handles root deletion, updates `selectedChild`, then normalizes

This is much richer than "truncate everything after index N".

#### 3. Local branch switcher depends on user -> assistant child variants

Original/local branch UI:

- `lib/widgets/conversation_view_v2/user_bubble.dart:66`
  - `_buildAssistantVariantSwitcher(...)`
- `lib/controllers/thread_manager.dart:515`
  - variant ids are simply `userNode.children`

This only works if regenerated assistants are siblings directly under the same user node.

### Why regenerate becomes `old -> new -> newnew`

#### 1. Backend regenerate uses a fake "prefix rebuild" helper

Backend-mode regenerate does not fork from the selected user checkpoint. It does this:

- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:731`
  - build `prefixMessages = visibleMessages.take(targetIndex + 1)`
- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:736`
  - call `_backendConversationSourceService.appendMessages(..., baseCheckpointId: '', messages: prefixMessages)`

The same helper exists centrally:

- `lib/widgets/conversation_view_v2.dart:612`
  - `_rebuildBackendPrefixCheckpoint(exclusiveEnd)` also calls `appendMessages(..., baseCheckpointId: '', messages: prefix)`

The code clearly assumes `baseCheckpointId: ''` means "start from empty and rebuild only this prefix".

#### 2. In the current backend implementation, `baseCheckpointId: ''` does not truncate history

Frontend `''` becomes backend `None`:

- `backend/services/conversation_source.py:357`
  - `_resolve_base_checkpoint_id()` returns `None` for `""`

Then `append_messages()` writes with no checkpoint id in config:

- `backend/services/conversation_source.py:196`
  - `graph.update_state(self._thread_config(conversation_id, checkpoint_id=base_checkpoint_id), ...)`

Because the source state uses `add_messages`, the write is merge/append semantics, not truncate semantics.

Minimal reproduction run against the same `LangGraph + add_messages` pattern used here:

1. write `[u1]`
2. append `[a1(old)]`
3. call `update_state(thread_only_config, messages=[u1])`
4. result is still `[u1, a1(old)]`, not `[u1]`
5. append `[a2(new)]`
6. result becomes `[u1, a1(old), a2(new)]`

That exactly matches the observed chaining behavior.

The same merge rule is also visible directly from `add_messages` itself:

- old state `[u1, a_old]` merged with `[u1]` stays `[u1, a_old]`
- then merged with `[a_new]` becomes `[u1, a_old, a_new]`

#### 3. Projection rebuild then turns those checkpoint lists into a linear assistant chain

Once the checkpoints look like:

- checkpoint 1: `[U1]`
- checkpoint 2: `[U1, A1(old)]`
- checkpoint 3: `[U1, A1(old)]`   (fake "prefix rebuild", tail not removed)
- checkpoint 4: `[U1, A1(old), A2(new)]`

Flutter reconstruction does:

- `lib/services/backend_conversation_source_service.dart:242`
  - parent of each message is previous message in that checkpoint list

So `A2(new)` gets parent `A1(old)`, not `U1`.

That is why the UI becomes:

- `U1 -> A1(old) -> A2(new)`

and the next regenerate becomes:

- `U1 -> A1(old) -> A2(new) -> A3(newnew)`

instead of sibling assistant variants under `U1`.

### Why delete currently fails

#### 1. There is no backend message-delete / node-delete API

Source API currently supports:

- append
- patch
- checkpoint selection
- clear whole source

See:

- `backend/api/conversation_source.py`

There is no endpoint equivalent to local `ConversationThread.removeNode(...)`.

#### 2. Backend-mode delete is only a prefix rollback shim

Backend delete does this:

- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:524`
  - compute prefix before the deleted message
- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:527`
  - if empty, `clearSource(...)`
- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:532`
  - else `selectCheckpoint(prefixCheckpointId)`

So even in the best case, backend delete means:

- "rewind conversation to the prefix before this message"

It does not mean:

- "delete this node but preserve/promote descendants like the original tree implementation"

#### 3. The rollback shim is currently built on the same broken fake-prefix assumption

The prefix checkpoint used by backend delete comes from:

- `lib/widgets/conversation_view_v2.dart:612`
  - `_rebuildBackendPrefixCheckpoint(...)`

which again writes:

- `appendMessages(..., baseCheckpointId: '', messages: prefix)`

Under current `add_messages` semantics, that does not reliably remove the tail.

So "无法删除" is explained by a combination of:

- migration not complete: delete semantics were downgraded from node deletion to prefix rollback
- concrete bug: the prefix rollback helper does not actually truncate the checkpoint state it is trying to rebuild

### Issue C: split replies and apparent "replay" of truncated content

### Confirmed conclusion

Code does not support the theory that regenerate simply skips the new request.

Backend regenerate still unconditionally proceeds into a fresh request after the prefix write/load:

- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:742`
  - backend regenerate reloads backend state
- `lib/widgets/conversation_view_v2/message_actions_sheet.dart:757`
  - then calls `_startAssistantResponse(...)`

So the stronger code-based explanation is:

- the broken prefix rebuild re-selects a checkpoint that still contains earlier assistant tail content
- Flutter immediately reconstructs and shows that stale chain
- the user can perceive this as "regenerate just吐出旧的截断内容"
- the actual request may still be issued afterwards, but it is starting from an already-wrong visible chain

In other words, Issue C currently looks like a downstream symptom of the same tree/prefix semantic mismatch, not an independent proof that `_startAssistantResponse()` is being skipped.

### Additional mismatch uncovered while comparing old tree vs current backend projection

Current Flutter-side projection keys nodes only by `message.id`:

- `lib/services/backend_conversation_source_service.dart:229`
  - `nodes.putIfAbsent(message.id, ...)`

But backend checkpoints can legitimately contain the same message id with different content across revisions, especially after `patch_message()`:

- `backend/services/conversation_source.py:231`
  - patched message keeps the same id

This means the current pseudo-tree cannot faithfully represent branch-specific same-id revisions the way a real checkpoint/read-model system should. That is a separate architectural limitation and can contaminate older branch views after edits.

### Test coverage gap that allowed this through

Backend tests currently verify explicit forking from a real checkpoint id:

- `backend/tests/test_conversation_source_api.py:79`
  - forking from `checkpoint_user` correctly produces `[user-1, assistant-2]`

That proves the backend can branch correctly when given the right base checkpoint.

What is not covered is the frontend-specific migration shim:

- `base_checkpoint_id = ""`
- rebuild-prefix-then-regenerate
- rebuild-prefix-then-delete

That exact untested path is where the current bug sits.

### Scope assessment

Issue 2 is partly a bug and partly an unfinished migration boundary:

- Bug:
  - backend-mode prefix rebuild assumes truncate semantics that current `LangGraph + add_messages` does not provide
- Not yet migrated:
  - backend-mode delete has no true node-delete contract matching old Flutter tree behavior
  - backend still does not expose a backend-native branch/read model; Flutter is still reconstructing tree semantics locally from checkpoint history

### Related flows likely affected by the same root cause

- backend user-message `保存并重发`
  - `lib/widgets/conversation_view_v2/message_actions_sheet.dart:238`
  - also depends on `_rebuildBackendPrefixCheckpoint(...)`
- any future backend-mode rollback/truncate flow built on `baseCheckpointId: ''`
- older-branch rendering after same-id message edits, due `message.id`-keyed pseudo-tree projection

## Issue 3. Error does not terminate UI loading state

### Reported symptoms

- When the backend encounters an error during streaming/chat, the UI can stay in a loading/streaming state instead of terminating cleanly.
- In the user's observed variant, restarting later can reveal the error block that was not shown immediately.

### Confirmed conclusion

This symptom currently mixes two different problems:

1. The specific "still animating, but restart later shows the error block" behavior is primarily the same same-id repaint problem already described in Issue 1.

2. A separate real cleanup bug also exists: backend-mode `_finalizeStreamingMessage()` does not guard its own backend persistence call. If `appendMessages(...)` throws during finalize, the rest of the cleanup path never runs, and `_isLoading` can remain stuck `true`.

3. Independently of both points above, HTTP-level streaming failures before SSE starts are still being swallowed by Dio because `validateStatus` accepts all status codes. That creates a silent-failure path, but it is not the same as the "restart later shows the error block" symptom.

### Evidence chain

#### 1. SSE error handling can already build and persist an error-tagged assistant message

When proxy SSE contains an error payload:

- `lib/adapters/proxy_openai_provider.dart`
  - `_tryParseStreamingPayload(...)` throws when parsed payload contains top-level `error`
- `lib/controllers/stream_output_controller.dart`
  - stream subscription `onError` forwards the error to `_startAssistantResponse(...)`
- `lib/widgets/conversation_view_v2/streaming.dart`
  - `onError` stores `_pendingFinalize`
  - `_finalizeStreamingMessage(...)` converts the error to `errorTag`
  - backend mode then builds `assistantMessage` with the same placeholder id and persists it through `_backendConversationSourceService.appendMessages(...)`

So the error message can already exist in the persisted conversation state.

#### 2. That persisted error message is still exposed to the Issue 1 repaint bug

After backend finalize succeeds:

- `lib/widgets/conversation_view_v2/streaming.dart`
  - backend mode applies `_applyBackendSourceSnapshot(...)`
- `lib/widgets/conversation_view_v2.dart`
  - `_applyBackendSourceSnapshot(...)` ends in `_syncConversationToChatController(...)`
- `lib/widgets/conversation_view_v2/scroll_and_highlight.dart`
  - `_syncConversationToChatController(...)` uses `_chatController.setMessages(...)`, not `updateMessage(...)`

Because the finalized error message keeps the same assistant id as the streaming placeholder, the visible row can keep rendering the old streaming placeholder until it is recycled. That is exactly the Issue 1 pattern:

- the conversation data already contains the error block
- the visible bubble still looks like an animating placeholder
- scroll/restart rebuilds the row
- the persisted error block becomes visible afterwards

That means the "restart后才会显示错误框" observation is not best explained by a missing error-propagation path. It is best explained by Issue 1's same-id row refresh bug occurring on an error-finalize flow.

#### 3. A separate confirmed bug exists in backend-mode finalize cleanup

`_finalizeStreamingMessage(...)` still has no try-catch around backend persistence:

- `lib/widgets/conversation_view_v2/streaming.dart`
  - `final snapshot = await _backendConversationSourceService.appendMessages(...)`
  - `_applyBackendSourceSnapshot(...)`
  - `setState(() { _isLoading = false; ... })`

If `appendMessages(...)` throws, the later cleanup code is skipped:

- `_applyBackendSourceSnapshot(...)` is not reached
- `_streamManager.removeStream(...)` is not reached
- `setState(() { _isLoading = false; ... })` is not reached

That is the real path that can leave the view logically stuck in loading state.

#### 4. Reveal tick currently calls finalize via `unawaited(...)`

The reveal tick triggers finalize in fire-and-forget mode:

- `lib/widgets/conversation_view_v2/streaming.dart`
  - several branches call `unawaited(_finalizeStreamingMessage(...))`

So any exception thrown from finalize is easy to lose completely. That amplifies the cleanup bug above.

#### 5. HTTP-level errors before SSE starts are still swallowed

- `lib/services/dio_service.dart`
  - `validateStatus: (status) => status != null`

This means Dio does not throw on 4xx/5xx HTTP responses. For streaming requests:

1. backend can return plain JSON error with HTTP 4xx/5xx before any SSE body starts
2. Dio still hands the body to the stream reader
3. `ProxyOpenAIProvider._tryParseStreamingPayload(...)` ignores non-`data: ` lines
4. stream ends normally, so `onDone` runs instead of `onError`
5. the placeholder can be removed with no error block at all

This is a separate silent-error path. It does not explain the "restart later shows error block" symptom, because in this path no error-tagged message is ever persisted.

### Failure mode matrix

| Error scenario | What happens | User-visible result |
|---|---|---|
| SSE error during streaming, finalize succeeds | error is persisted under same message id, then UI sync uses `setMessages()` | Can still look like endless streaming until scroll/restart, because Issue 1 blocks immediate row refresh |
| SSE error during streaming, finalize persistence throws | finalize aborts before cleanup completes | Real stuck loading / stream cleanup failure |
| HTTP 4xx/5xx before SSE starts | Dio swallows status, stream ends as empty normal completion | No error bubble, placeholder may just disappear |

### Scope assessment

Issue 3 therefore is not one single root cause:

- The user's "restart后显示错误框" symptom is primarily an Issue 1 repaint/update problem.
- A separate real bug still exists in backend-mode finalize cleanup when `appendMessages(...)` throws.
- Another separate bug exists in the pre-SSE HTTP error path because Dio suppresses bad status handling.

## Issue 5. Normal chat mode unexpectedly retries

### Reported symptoms

- In normal (non-retry) chat, the system appears to retry requests multiple times when it shouldn't.

### Confirmed conclusion

Normal chat does currently have automatic retry/fallback behavior, but the active layers are all on the backend side.

The current code shows four important facts:

1. Flutter's `BackendRoutingProvider` is not in the normal request path when backend mode is enabled. The app force-selects `ProxyOpenAIProvider`, so the previously documented "frontend fallback to direct" is not part of the current runtime chain.

2. LiteLLM Router retry is globally enabled for normal chat on any LiteLLM path via `llm_num_retries = 2`. There is no RP-only gate around this.

3. The current default routing semantics still tend to resolve to backend `auto`, not backend `proxy`, because the sync layer omits default `direct` hints and the backend interprets missing routing hints as implicit `auto`.

4. Because of point 3, normal chat can stack backend-side Router retry with backend-side Gemini-native pre-attempt and backend-side httpx fallback.

### Evidence chain

#### 1. Frontend currently does not use `BackendRoutingProvider` for normal backend chat

- `lib/adapters/ai_provider.dart`
  - `ProviderFactory.createProviderWithRouting(...)` returns `ProxyOpenAIProvider(config)` whenever `pythonBackendEnabled == true`
  - the code explicitly ignores `config.backendMode` in that branch
- `lib/adapters/backend_routing_provider.dart`
  - this class still exists, but it is bypassed by the current factory logic

So the current app does not have an extra client-side "proxy failed, then direct retry" layer in normal backend mode.

#### 2. LiteLLM retry is globally configured for ordinary chat traffic

- `backend/config.py`
  - `llm_num_retries: int = 2`
  - `use_litellm_router: bool = True`
- `backend/services/litellm_service.py`
  - `_get_router(...)` always passes `"num_retries": self.settings.llm_num_retries` when Router is enabled

There is no code path here that says "only enable retries for RP". If a normal chat request goes through LiteLLM, it inherits this retry budget.

#### 3. Default provider sync still tends to produce implicit backend `auto`

Proxy chat requests do not upload routing mode inline:

- `lib/adapters/proxy_openai_provider.dart`
  - `_buildRequestBody(...)` sends `provider_id`, but not `backend_mode`

Provider sync omits the default `direct` bundle:

- `lib/services/backend_provider_registry_service.dart`
  - `_buildPayload(...)` only persists `backend_mode` when it is not `direct`
  - it only persists fallback settings for `auto`, or `fallback_enabled = false`

Backend runtime treats missing hints as implicit `auto`:

- `backend/services/runtime_routing_service.py`
  - `_get_route_mode(...)` returns `"auto"` when `provider.backend_mode is None`
- `backend/models/provider_registry.py`
  - `to_runtime_provider()` uses normalized routing hints
  - default/implicit routing hints are preserved as `None`, which runtime later interprets as `"auto"`

This creates a subtle mismatch:

- the Flutter mirror can still look like `backendMode = direct`
- the backend runtime can still behave as implicit `auto`

That mismatch is one reason the retry behavior is surprising in "normal chat".

#### 4. Backend `auto` mode can stack multiple server-side attempts

- `backend/services/runtime_routing_service.py`
  - Gemini models in `auto` can try `GeminiNativeService` first
  - then fall through to LiteLLM primary
  - then can still fall back to `LLMProxyService` httpx on eligible pre-chunk failures
- the fallback guard checks `has_emitted_chunk`, so this only happens before visible output starts

That means the effective server-side attempt budget is:

- backend `proxy` route:
  - LiteLLM path with Router retry enabled
- backend implicit `auto`, non-Gemini:
  - LiteLLM path with Router retry enabled
  - optional httpx fallback afterwards
- backend implicit `auto`, Gemini:
  - optional Gemini native pre-attempt
  - LiteLLM path with Router retry enabled
  - optional httpx fallback afterwards

If LiteLLM interprets `num_retries = 2` as "initial call + 2 retries", the configured upstream-call budget is up to:

- `proxy`: 3 calls on the LiteLLM path
- implicit `auto`, non-Gemini`: 4 calls
- implicit `auto`, Gemini`: 5 calls

The exact inner retry behavior belongs to LiteLLM, but the important code-level fact is already sufficient: normal chat requests are explicitly opting into retry by passing `num_retries = 2`.

### Scope assessment

Issue 5 is confirmed, but the current shape is slightly narrower than earlier notes suggested:

- The currently active unwanted retries are backend-side normal-chat behavior, not an RP-only path.
- The current app is not stacking Flutter `BackendRoutingProvider` fallback on top, because that provider is bypassed.
- The real design problem is:
  - LiteLLM retry is globally enabled for normal chat
  - implicit backend `auto` can add even more fallback stages
  - the UI mirror can make runtime routing look more "direct" than it actually is

## Issue 6. Additional backend-mode symptoms (2026-04-09 follow-up)

### Reported symptoms

- A. Regenerate outputs old truncated content instead of the new LLM response.
- B. First message in a new conversation briefly shows two assistant headers, then collapses to one.
- C. Conversation page goes blank after app restart; messages appear only after sending a new message.
- D. Regenerate can occasionally swallow the new message entirely.

### Investigation results

#### Symptom A: Regenerate outputs old truncated content

**Confirmed root cause**: This is a direct consequence of Issue 2's `baseCheckpointId: ''` + `add_messages` merge semantics.

Evidence chain:

1. User clicks regenerate on an assistant message
2. Backend regenerate path at `message_actions_sheet.dart:736` calls:
   ```
   appendMessages(baseCheckpointId: '', messages: prefixMessages)
   ```
3. `baseCheckpointId: ''` resolves to `None` in backend (`conversation_source.py:357`)
4. `add_messages` merge semantics: the old assistant message is NOT removed from the checkpoint
5. `_loadBackendConversationState(autoFollow: false)` reloads the state at line 742
6. The loaded state still contains the old assistant message (merge didn't truncate)
7. `_startAssistantResponse` at line 757 builds prompt from `_getThread()` → `buildActiveMessageChain()` → `safeHistory` at `streaming.dart:218-224`
8. `safeHistory` includes the old (truncated) assistant content because it was never removed from the checkpoint
9. LLM receives the old assistant content as history context and may continue from that point or repeat similar content
10. Even if the LLM produces genuinely new content, the UI thread contains the old assistant as a persisted node, so the new reply appears as a continuation after the old one (Issue 2's chaining behavior)

The combination means:
- The prompt sent to the LLM **includes** the old assistant answer as history
- The new response is appended **after** the old one in the checkpoint
- The user perceives this as "regenerate just replays old content"

**This is Issue 2, not a new bug**. The fix requires implementing correct checkpoint fork instead of `baseCheckpointId: ''` prefix rebuild.

#### Symptom B: Two assistant headers on first message

**Confirmed root cause**: Race condition between `_refreshBackendProjectionInBackground` and `_startAssistantResponse` placeholder insertion.

Evidence chain — timeline for first message in backend mode:

1. `_sendMessage()` at `streaming.dart:50-56`:
   - `appendMessages(userMsg)` → backend writes user message to checkpoint
   - `_applyBackendSourceSnapshot(snapshot)` → `setMessages([user])` into chat controller
   - `_refreshBackendProjectionInBackground()` → fires `unawaited(_loadBackendConversationState())`

2. `_startAssistantResponse()` at `streaming.dart:170-174`:
   - Creates assistant placeholder
   - `_chatController.insertMessage(placeholder, animated: true)` → chat controller now has `[user, placeholder]`

3. **Meanwhile**, `_loadBackendConversationState` completes asynchronously:
   - `_applyBackendProjection()` at `conversation_view_v2.dart:561-571`
   - `_syncConversationToChatController()` at `scroll_and_highlight.dart:14-30`
   - Builds `msgs = [user]` from thread (backend has no assistant yet)
   - Detects active `_activeAssistantPlaceholder` → appends it: `msgs = [user, placeholder]`
   - `_chatController.setMessages([user, placeholder])` replaces the list

4. But between step 2 and step 3, the streaming has already started producing content, and `_handleStreamFlush` is updating the placeholder via `_chatController.updateMessage`.

5. The `setMessages` from step 3 does a diff against the current list `[user, placeholder_with_content]`. Because the placeholder has been updated (different metadata/text), the diff may see it as a `change` and do remove+insert, causing a visual flash of two headers.

**Fix**: `_refreshBackendProjectionInBackground` in `_sendMessage` should not be called until after `_startAssistantResponse` completes, or should be suppressed during active streaming. The simplest fix is to move it to after the assistant response finalize, or gate it behind `_isLoading`.

#### Symptom C: Blank conversation page after restart

**Confirmed root cause**: Backend connectivity gap during app startup.

Evidence chain:

1. `initState()` at `conversation_view_v2.dart:236-244`:
   ```dart
   scheduleMicrotask(() async {
     if (ai.ProviderFactory.pythonBackendEnabled) {
       await _loadBackendConversationState(autoFollow: false);
     } else {
       _syncConversationToChatController();
     }
   });
   ```

2. When backend mode is enabled, `_loadBackendConversationState` is called immediately
3. If the backend is not yet running (port being reclaimed, process not started), this call fails
4. The `catch` block at `conversation_view_v2.dart:555-558` only does `debugPrint`, no fallback:
   ```dart
   } catch (e) {
     if (loadEpoch != _backendConversationLoadEpoch) return;
     debugPrint('[ConversationViewV2] backend conversation load failed: $e');
   }
   ```
5. Chat controller remains empty (no `setMessages` called), page shows blank
6. No retry mechanism exists for the initial load failure
7. When user sends a new message, `_sendMessage` triggers `appendMessages` + `_applyBackendSourceSnapshot`, which populates the chat controller — page comes alive

**Fix**: Add a retry-with-backoff for the initial `_loadBackendConversationState` call, or fall back to showing cached/placeholder state when backend is unreachable.

#### Symptom D: Regenerate swallows new message

**Confirmed root cause**: Same Issue 2 prefix-rebuild failure + async projection race.

Two mechanisms can cause this:

**Mechanism 1** (Issue 2 core): `baseCheckpointId: ''` prefix rebuild doesn't truncate. The regenerated assistant message is appended after the old one in the checkpoint. If the `_loadBackendConversationState` that runs after finalize picks up a checkpoint where the new message is not the last visible message (e.g., because selected_checkpoint_id hasn't been updated yet), the new content may not appear in the visible chain.

**Mechanism 2** (async projection race): Same as Symptom B's race condition. After regenerate's `_startAssistantResponse` completes and finalizes:
- `_refreshBackendProjectionInBackground` is called at finalize (`streaming.dart:1098`)
- This fires an async `_loadBackendConversationState`
- If the regenerate's `_loadBackendConversationState` (from `message_actions_sheet.dart:742`) hasn't fully propagated the new checkpoint selection before this background refresh, the background refresh may load an older projection and overwrite the visible chain

This is harder to reproduce because it depends on exact timing of multiple async operations.

### Summary

| Symptom | Root cause | Is new bug? |
|---------|-----------|-------------|
| A. Regenerate outputs old content | Issue 2: `baseCheckpointId: ''` merge semantics + old content in prompt | No, existing Issue 2 |
| B. Two assistant headers | Race: `_refreshBackendProjectionInBackground` vs placeholder insertion | Yes, new race condition |
| C. Blank page after restart | No retry on initial backend load failure | Yes, new resilience gap |
| D. Regenerate swallows message | Issue 2 + async projection race | Partially new (race), partially Issue 2 |
