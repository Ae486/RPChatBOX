# Flutter Data Storage Migration Status Review

Date: 2026-04-10
Scope: check whether Flutter-side data storage has been fully migrated to backend, and classify the current storage boundary into migrated, still needs migration, and does not need migration.
Status: completed

## 1. Executive Conclusion

Current Flutter-side data storage has **not** been fully migrated to backend.

The correct description is:

- in `pythonBackendEnabled == true` mode, the main conversation/storage truth has already moved to backend for the current migration slice
- Flutter still keeps some local mirrors, compatibility layers, and frontend-local state
- the old local Hive / SharedPreferences paths still exist as fallback for direct mode and rollback

So the project is currently in a **partial cutover / transitional dual-path state**, not a full frontend-storage-to-backend migration.

This review only focuses on storage ownership and true-source boundaries.
It does not re-open the bug analysis already documented in:

- `docs/review/2026-04-09-backend-migration-bug-investigation.md`

## 2. Overall Classification

### 2.1 Already Migrated to Backend Truth

These items are already backend-owned for the current scope when backend mode is enabled.

#### A. Conversation metadata

Migrated:

- conversation list
- create conversation
- rename conversation
- delete conversation
- conversation metadata fields such as:
  - `title`
  - `system_prompt`
  - `role_id`
  - `role_type`
  - `latest_checkpoint_id`
  - `selected_checkpoint_id`
  - archive / pin related flags

Evidence:

- Flutter read/write path:
  - `lib/providers/chat_session_provider.dart`
  - `lib/services/backend_conversation_service.dart`
- backend ownership:
  - `backend/models/conversation_store.py`
  - `backend/services/conversation_store.py`
  - `backend/api/conversations.py`

Conclusion:

- conversation metadata is already backend true-source in backend mode
- Flutter still keeps in-memory objects for UI state, but they are no longer the durable truth

#### B. Conversation generation-affecting settings

Migrated:

- `selected_provider_id`
- `selected_model_id`
- `parameters`
- `enable_vision`
- `enable_tools`
- `enable_network`
- `enable_experimental_streaming_markdown`
- `context_length`

Evidence:

- Flutter read/write path:
  - `lib/services/model_service_manager.dart`
  - `lib/services/backend_conversation_service.dart`
- backend ownership:
  - `backend/models/conversation_store.py`
  - `backend/api/conversations.py`

Conclusion:

- these settings are already backend-owned in backend mode
- Flutter keeps a local cache map for runtime/UI convenience, but not as the intended true source

#### C. Source-thread / message persistence

Migrated:

- append message
- patch message
- select checkpoint
- clear source
- source checkpoint history persistence

Evidence:

- Flutter client:
  - `lib/services/backend_conversation_source_service.dart`
- backend ownership:
  - `backend/services/conversation_source.py`
  - `backend/api/conversation_source.py`

Conclusion:

- backend already owns source persistence using LangGraph checkpoints
- this is the main storage migration foundation for message tree migration

#### D. Provider / model registry

Migrated for current runtime truth:

- provider CRUD
- model CRUD
- backend-side provider/model resolution

Evidence:

- Flutter path:
  - `lib/services/model_service_manager.dart`
- backend APIs:
  - `backend/api/providers.py`
  - `backend/api/provider_models.py`
- backend persistence:
  - `backend/services/provider_registry.py`
  - `backend/services/model_registry.py`

Important boundary:

- this slice is already backend-first
- but backend persistence is currently JSON-file-based (`storage/providers.json`, `storage/models.json` style), not PostgreSQL app-table persistence

Conclusion:

- provider/model truth has already moved to backend for the current scope
- this is migrated in ownership terms, but not yet migrated to the final database form

### 2.2 Not Yet Migrated But Still Needs Migration

These items are still not fully backend-owned and should continue moving to backend if the migration target remains unchanged.

#### A. Backend-native branch / tree read model

Current reality:

- backend stores checkpoints
- Flutter still reconstructs a pseudo-tree locally from checkpoint history

Evidence:

- Flutter reconstruction:
  - `lib/services/backend_conversation_source_service.dart`
  - `_buildProjection(...)`
- current chat rendering still depends on reconstructed `ConversationThread`

Conclusion:

- source persistence migrated, but source-tree read semantics are not fully migrated
- this is one of the main unfinished storage boundaries

#### B. Conversation summary persistence

Current reality:

- summary still lives on Flutter `Conversation`
- summary write logic is still local

Stored fields still local:

- `summary`
- `summaryRangeStartId`
- `summaryRangeEndId`
- `summaryUpdatedAt`

Evidence:

- model:
  - `lib/models/conversation.dart`
- summary logic:
  - `lib/services/conversation_summary_service.dart`

Conclusion:

- summary storage has not yet moved to backend
- if summary is intended to survive reload/restart/cross-device/backend truth migration, it still needs backend ownership

#### C. Durable attachment business data

Current reality:

- sent message snapshots can already travel through backend source messages
- but backend app-table ownership for attachments is not yet implemented

Still missing on backend:

- attachment metadata table
- storage ownership / storage key
- conversation attachment references as durable business data

Evidence:

- plan/reference:
  - `docs/migration/13-conversation-session-postgres-langgraph-plan.md`

Conclusion:

- attachment history snapshots are partially covered
- durable attachment storage/ownership is not migrated yet

#### D. Custom roles / assistant identity data

Current reality:

- custom roles are still stored locally in SharedPreferences

Evidence:

- `lib/services/custom_role_service.dart`
- related page logic still works against local storage:
  - `lib/pages/custom_roles_page.dart`

Conclusion:

- if custom role / assistant identity is meant to become backend-owned product data, this still needs migration
- this aligns with the longer-term `assistants` / backend-owned identity direction in migration docs

#### E. MCP server configuration and MCP runtime ownership

Current reality:

- MCP server configs are still stored in local Hive
- MCP client/runtime still runs in Flutter

Evidence:

- config storage:
  - `lib/services/mcp_config_service.dart`
- client/runtime:
  - `lib/services/mcp_client_service.dart`

Conclusion:

- this is not migrated
- if MCP/tool runtime is to become backend-owned, both config storage and execution ownership still need migration

#### F. RP memory / RP durable state

Current reality:

- RP data is still fully local in Hive

Evidence:

- `lib/services/roleplay/rp_memory_repository.dart`

Boxes still local:

- `rp_story_meta`
- `rp_entry_blobs`
- `rp_ops`
- `rp_snapshots`
- `rp_proposals`

Conclusion:

- RP storage is not migrated
- this is explicitly outside the completed migration slice and still belongs to future backend redesign work

### 2.3 Does Not Need Backend Migration

These items are frontend-local UX or device-local state and do not need to become backend truth.

#### A. Current selected conversation id

Current reality:

- still stored locally as `current_conversation_id`

Evidence:

- `lib/providers/chat_session_provider.dart`
- `lib/services/hive_conversation_service.dart`

Conclusion:

- this is UI selection state
- it does not need to become backend durable truth by default

#### B. Scroll position and similar view state

Current examples:

- `scrollIndex`
- open panels
- local loading / placeholder state
- input draft and similar page-level UI state

Evidence:

- `lib/models/conversation.dart` still contains `scrollIndex`
- migration plan explicitly treats such data as frontend-local state

Conclusion:

- this should remain frontend-local
- it is not part of backend true-source migration

#### C. Temporary attachment staging before submit

Current reality:

- `ConversationSettings.attachedFiles` is used as composer-side staging before send
- after send, files are cleared from this local staging state

Evidence:

- `lib/models/conversation_settings.dart`
- `lib/chat_ui/owui/composer/owui_composer.dart`
- `lib/widgets/conversation_view_v2/streaming.dart`

Conclusion:

- temporary pre-submit attachment staging is frontend workflow state
- it does not need backend persistence as truth before submission

#### D. Local device preferences and local-only operational state

Examples:

- `python_backend_enabled`
- legacy/global `chat_settings`
- local token usage statistics
- display/cache preferences

Evidence:

- `lib/pages/settings_page.dart`
- `lib/services/storage_service.dart`

Conclusion:

- these are device-local preferences or local operational counters
- they do not need backend migration as part of conversation/storage true-source work

## 3. Important Transitional Boundary

The biggest source of confusion is:

- some Flutter local storage still exists
- but not all existing local storage is still a true source

Current transitional split should be read as:

- backend mode:
  - conversation metadata/settings/source are already backend truth for the current migration slice
- direct mode / rollback path:
  - old Flutter local storage still exists and remains runnable
- migration gap:
  - Flutter still rebuilds tree semantics locally from backend checkpoint history
  - some product data classes such as summary / attachments / MCP / RP are still not backend-owned

This means:

- the migration is real
- but it is not complete
- and it is not accurate to describe the current system as “Flutter storage has been fully migrated to backend”

## 4. Final Answer to the Task Question

### Has Flutter-side data storage been fully migrated to backend?

No.

### Already migrated

- conversation metadata in backend mode
- conversation generation settings in backend mode
- source-thread / checkpoint persistence in backend mode
- provider/model runtime registry ownership for the current scope

### Not yet migrated but should still migrate

- backend-native branch/tree read model
- conversation summaries
- durable attachment business data
- custom role / assistant identity data
- MCP config/runtime ownership
- RP memory / RP durable storage

### Does not need backend migration

- current selected conversation id as UI selection state
- scroll position and similar view-only state
- temporary attachment staging before send
- device-local preferences and local token statistics

## 5. Recommended Interpretation for Follow-up Work

If follow-up work continues to focus on storage migration, the next storage priorities should be:

1. stop relying on Flutter-side pseudo-tree reconstruction and move to a backend-native source read model
2. move summary storage to backend if summary remains part of durable conversation state
3. design backend attachment metadata ownership instead of keeping only local/file-path-oriented snapshots
4. keep frontend-local UX state local instead of over-migrating it

