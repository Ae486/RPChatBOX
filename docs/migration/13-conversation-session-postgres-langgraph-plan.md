# Conversation / Session True-Source Plan

Last Updated: 2026-04-09
Status: draft for implementation handoff

## 1. Purpose

This document defines the target backend true-source design for:

- conversation / session data
- source message tree / branching chat
- conversation settings
- summary / attachment metadata boundaries

The goal is not to port Flutter storage as-is.

The goal is to:

- understand current persisted data and technical debt
- map durable business data to PostgreSQL
- use LangGraph for source-tree / checkpoint semantics where it is a better fit
- avoid keeping Flutter-era storage compromises when Python/backend frameworks already solve the problem better

## 2. Confirmed Decisions

- backend will become the true source for conversation / session data
- PostgreSQL is the primary database
- source message tree semantics should follow LangGraph, not the current Flutter tree implementation
- delete semantics should follow LangGraph-style branch / checkpoint behavior for now
  - no node rewiring
  - no child promotion
- two edit modes must remain available:
  - `save`: patch current message, do not replay downstream generation
  - `save and send`: for user messages, fork from the parent checkpoint and continue generation
- local historical conversation data is not important and may be discarded
- provider / model data must be retained
- conversation read and write paths should switch to backend together, not via long-lived dual-source transition

## 3. Current Flutter Storage Inventory

### 3.1 Conversation

Current model: `lib/models/conversation.dart`

Current stored fields:

- `id`
- `title`
- `messages`
- `createdAt`
- `updatedAt`
- `systemPrompt`
- `scrollIndex`
- `roleId`
- `roleType`
- `threadJson`
- `activeLeafId`
- `summary`
- `summaryRangeStartId`
- `summaryRangeEndId`
- `summaryUpdatedAt`
- `messageIds`

Current persistence shape:

- `Conversation` metadata is stored in Hive box `conversations`
- all messages are stored separately in Hive box `messages`
- current conversation id is stored separately in Hive box `settings`

Key issue:

- `Conversation` stores both:
  - `threadJson` + `activeLeafId` as the tree source
  - `messages` as the active-chain snapshot
  - `messageIds` as all-known-message ids

This is redundant and causes semantic drift.

### 3.2 Message

Current model: `lib/models/message.dart`

Current stored fields:

- `id`
- `content`
- `isUser`
- `timestamp`
- `inputTokens`
- `outputTokens`
- `modelName`
- `providerName`
- `attachedFiles`
- `parentId`
- `editedAt`
- `thinkingDurationSeconds`

Observations:

- `parentId` duplicates tree structure information that is also reconstructed in `ConversationThread`
- `modelName` / `providerName` are display-oriented historical metadata, not routing truth
- `attachedFiles` stores only lightweight snapshots, not backend-managed file ownership

### 3.3 Conversation Settings

Current model: `lib/models/conversation_settings.dart`

Current stored fields:

- `conversationId`
- `selectedProviderId`
- `selectedModelId`
- `parameters`
- `attachedFiles`
- `enableVision`
- `enableTools`
- `enableNetwork`
- `enableExperimentalStreamingMarkdown`
- `contextLength`
- `createdAt`
- `updatedAt`

Current persistence:

- stored in `SharedPreferences` via `ModelServiceManager`

Observations:

- true conversation settings are currently split away from conversation persistence
- attachment staging lives inside settings, which mixes UI workflow state with durable conversation configuration

### 3.4 Attached Files

Current model: `lib/models/attached_file.dart`

Important split:

- `AttachedFile`
  - full local file metadata, includes `path`, `sizeBytes`, `metadata`
- `AttachedFileSnapshot`
  - lightweight message snapshot with `id`, `name`, `path`, `mimeType`, `type`

Current reality:

- message history stores local file references
- this was tolerable for local Flutter desktop persistence
- it is not a good backend true-source shape for multi-device or cloud deployment

### 3.5 Current Conversation / Session State

Current owner: `lib/providers/chat_session_provider.dart`

Current responsibilities:

- load all conversations from local storage
- track current selected conversation
- create / switch / delete / rename conversations
- persist current conversation id locally

This means `session` is still frontend-owned.

## 4. Current Tree Implementation and Its Debt

### 4.1 Current Source Tree Shape

Current model: `lib/models/conversation_thread.dart`

Core fields:

- `conversationId`
- `nodes`
- `rootId`
- `selectedChild`
- `activeLeafId`

Each `ThreadNode` stores:

- `id`
- `parentId`
- `message`
- `children`

Current visible chat list is not the full tree.
It is the active-chain projection produced by `buildActiveChain()`.

### 4.2 Current Technical Debt

Documented explicitly in:

- `docs/debug/thread-message-lookup-debt.md`

Key debt items:

- `conversation.messages` is only the active-chain snapshot, but is easy to misread as full history
- `threadJson` may be loaded multiple times through different lookup paths
- non-active branch messages rely on extra lookup plumbing (`getMessageById`)
- current storage keeps:
  - message box
  - `messageIds`
  - active snapshot
  - `threadJson`

This is a Flutter-era compromise caused by local Hive storage and UI convenience.

### 4.3 Current Delete Semantics

Current delete behavior is implemented by `ConversationThread.removeNode()`.

Important characteristics:

- if a node is a simple leaf with no siblings, it is removed directly
- if a node has children, children are promoted to the parent
- if the root has multiple children, only the currently selected child branch is kept and others are cascade-deleted

This is workable for local UI, but it is not standard branching-chat semantics and should not be carried forward as the target model.

## 5. PostgreSQL-Side Design Principles

Primary references:

- PostgreSQL `uuid`: https://www.postgresql.org/docs/current/datatype-uuid.html
- PostgreSQL `jsonb`: https://www.postgresql.org/docs/current/datatype-json.html
- PostgreSQL constraints / FKs: https://www.postgresql.org/docs/current/ddl-constraints.html

### 5.1 Use Native `uuid`

PostgreSQL provides native `uuid` support and can generate UUIDv4 / UUIDv7.

Recommendation:

- use `uuid` primary keys for backend-owned durable ids
- stop inheriting frontend timestamp-based ids as the long-term id strategy

### 5.2 Use Relational Tables for Stable Business Data

PostgreSQL foreign keys and constraints are strong fits for:

- conversation ownership / assistant binding
- settings rows
- summary rows
- attachment metadata rows
- pin / archive / delete flags

Recommendation:

- use normal relational tables for stable, query-heavy business data
- do not store the whole conversation system as one giant JSON document

### 5.3 Use `jsonb` Carefully

PostgreSQL docs recommend `jsonb` for most application JSON use cases because it is faster to process and supports indexing.

However, the docs also warn that updating a large JSON document still locks the whole row.

Recommendation:

- use `jsonb` only for flexible metadata and parameter blobs
- do not use one mutable `jsonb` blob as the primary source of the whole conversation tree

Good `jsonb` candidates:

- model generation parameter blobs
- optional message metadata
- optional attachment metadata
- optional read-model payload caches

Bad `jsonb` candidates:

- the whole conversation tree as a single mutable row
- all checkpoints for a thread in one row

## 6. LangGraph-Side Design Principles

Primary references:

- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph branching chat: https://docs.langchain.com/oss/python/langchain/frontend/branching-chat

### 6.1 What LangGraph Is Good At

LangGraph gives us:

- `thread_id` as the persisted unit of graph state
- checkpoint history
- replay from prior checkpoints
- `update_state()` to create a new checkpoint without mutating the original
- branching chat semantics using:
  - `branch`
  - `branchOptions`
  - `firstSeenState.parent_checkpoint`
- production-grade PostgreSQL checkpoint storage via `langgraph-checkpoint-postgres`

### 6.2 What LangGraph Should Own Here

LangGraph should own the source-tree / branch / checkpoint truth for the conversation thread.

Recommended ownership:

- branch history
- checkpoint lineage
- replay / regenerate fork points
- edit-and-send fork points
- time-travel / rollback foundation for source history

### 6.3 What LangGraph Should Not Own Alone

LangGraph should not be the only storage layer for the product.

Business data still needs normal app tables for:

- conversation list metadata
- assistant binding
- pin / archive / delete flags
- settings
- summaries
- attachment ownership / metadata
- later proposal / task / RP scope data

## 7. Recommended Target Split

### 7.1 PostgreSQL App Tables

Recommended durable app tables:

- `assistants`
  - or reuse/bridge existing role identity model later
- `conversations`
- `conversation_settings`
- `conversation_summaries`
- `attachments`
- optional `conversation_attachment_refs`
- optional `conversation_read_models`
- later:
  - `tasks`
  - `proposals`
  - `rollback_snapshots`

Suggested `conversations` columns:

- `id uuid primary key`
- `assistant_id uuid null`
- `assistant_type text null`
- `title text not null`
- `system_prompt text null`
- `latest_checkpoint_id uuid/text null`
- `last_activity_at timestamptz not null`
- `pinned_at timestamptz null`
- `archived_at timestamptz null`
- `deleted_at timestamptz null`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

Suggested `conversation_settings` columns:

- `conversation_id uuid primary key references conversations(id)`
- `selected_model_id text/uuid null`
- `parameters jsonb not null`
- `enable_vision boolean not null`
- `enable_tools boolean not null`
- `enable_network boolean not null`
- `context_length integer not null`
- `updated_at timestamptz not null`

Suggested `conversation_summaries` columns:

- `conversation_id uuid not null references conversations(id)`
- `branch_id text null`
- `checkpoint_id text null`
- `summary jsonb/text not null`
- `range_start_message_id text null`
- `range_end_message_id text null`
- `updated_at timestamptz not null`

Suggested `attachments` columns:

- `id uuid primary key`
- `conversation_id uuid not null`
- `storage_key text not null`
- `original_name text not null`
- `mime_type text not null`
- `size_bytes bigint not null`
- `kind text not null`
- `metadata jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null`

### 7.2 LangGraph Persistence

Recommended mapping:

- `thread_id = conversation_id`
- checkpointer:
  - `PostgresSaver` / `AsyncPostgresSaver`
- source tree truth:
  - checkpoints + checkpoint history
- branch switching:
  - use frontend-facing message metadata derived from LangGraph branching semantics

This removes the need to keep Flutter-era source duplication as truth:

- no `threadJson` as primary truth
- no `activeLeafId` as primary truth
- no `messageIds` list as primary truth
- no `conversation.messages` active snapshot as the durable source

### 7.3 Frontend Local State

Keep frontend-local only for:

- input draft
- scroll position
- open panels / tabs
- temporary attachment staging before submit
- ephemeral loading / placeholder state

Do not keep frontend-local as truth for:

- conversation list
- current branch
- source history
- conversation settings that affect generation

## 8. How Existing Flutter Complexity Can Be Reduced

### 8.1 Remove Active Snapshot Duplication as Durable Truth

Current Flutter keeps:

- full message store
- tree
- active-chain snapshot
- id index

Backend target should not.

Recommended backend truth:

- LangGraph checkpoint history for source state
- backend read model derived from the currently selected branch / checkpoint

### 8.2 Remove Message Lookup Pass-Through Debt

Current Flutter needed `getMessageById` plumbing because:

- active chain and full tree were stored separately

Backend target:

- the source tree is reconstructed from checkpoints
- UI messages come from backend read models

This removes the need for the `conversation.messages` vs `messageBox` workaround.

### 8.3 Replace Custom Tree Repair With Framework Persistence

Current `ThreadManager` validates and repairs:

- malformed `threadJson`
- orphan nodes
- invalid `selectedChild`
- active leaf mismatch

Backend target:

- use LangGraph checkpoint lineage as authoritative source
- avoid app-level self-healing on a hand-rolled tree format unless absolutely necessary

### 8.4 Use LangGraph `update_state()` for `save`

The `save` edit mode should remain, but this does not necessarily require a separate custom tree engine.

LangGraph persistence docs state that `update_state()` creates a new checkpoint with updated values and does not mutate the original checkpoint.

Recommendation:

- implement `save` as application-layer state patching over LangGraph
- this preserves the product requirement without reusing the Flutter tree implementation

This is still app-specific semantics, but it can lean on LangGraph instead of bypassing it completely.

### 8.5 Use Parent Checkpoints for `save and send`

Branching chat docs explicitly define:

- edit a user message by getting `parent_checkpoint`
- submit the edited input with that checkpoint
- LangGraph creates a new branch

Recommendation:

- implement `save and send` exactly this way
- do not preserve Flutter's current "mutate old user then branch assistant" behavior

## 9. Deletion Semantics for Phase 1

Confirmed direction:

- follow LangGraph-style semantics
- do not port Flutter's child-promotion delete behavior

Phase 1 recommendation:

- leaf delete:
  - current visible chain falls back to the parent checkpoint
- deleting a middle node:
  - current branch is truncated before that point
  - or hidden from the visible branch selection
- deleting a branch version:
  - hide or de-select the branch
- deleting a conversation:
  - soft-delete / archive the conversation record

Do not implement in Phase 1:

- node rewiring
- child promotion
- root special-case branch pruning logic from Flutter

## 10. Migration Strategy

### 10.1 What Must Be Preserved

- provider / model data
- current frontend-visible behavior for:
  - conversation list
  - branch switching
  - regenerate
  - save
  - save and send

### 10.2 What Does Not Need to Be Migrated

- old local conversation history
- old Hive thread state
- old current-conversation local ids

Because test data is disposable, we should avoid building a complicated import path for old conversations.

### 10.3 Recommended Cutover

1. Keep provider / model registry as-is on backend
2. Build PostgreSQL app tables for conversation metadata / settings / summaries / attachments
3. Build LangGraph-backed source-thread persistence using PostgreSQL checkpointer
4. Build backend read-model API for:
   - conversation list
   - conversation detail
   - visible active chain
   - branch metadata for switcher
5. Switch Flutter conversation reads to backend
6. Switch Flutter conversation writes to backend in the same rollout
7. Stop using Hive conversation data as truth
8. Optionally clear local Hive conversation storage after successful cutover

## 11. Minimal Correctness Requirements

Migration should not be considered complete until the following all hold:

- create conversation works
- rename / pin / archive works
- conversation list sorting follows:
  - pinned first
  - then `last_activity_at` descending within an assistant
- send message appends to the current visible chain
- regenerate creates a new assistant branch
- branch switch updates the downstream visible chain
- `save` patches the current message without replay
- `save and send` on a user message creates a new branch from the parent checkpoint
- restart / reload restores:
  - conversation list
  - current visible branch
  - conversation settings
- summary remains aligned with the selected branch / checkpoint

## 12. Recommended Framework Stack

### Use Directly

- `FastAPI`
- `SQLModel`
- `langgraph-checkpoint-postgres`
- `PostgresSaver` / `AsyncPostgresSaver`

### Use Later When Needed

- `PostgresStore` for cross-thread durable memory
- `pgvector` for RAG / embeddings
- later durable workflow / task runtime for asynchronous agents

### Do Not Recreate Without Need

- do not recreate a custom tree persistence layer if LangGraph checkpoints already cover the source-tree need
- do not recreate a JSON self-healing tree loader like the current Flutter `ThreadManager`
- do not recreate local-Hive-style snapshot duplication on the backend

## 13. Final Recommendation

For the backend true-source migration:

- store stable business data in PostgreSQL tables
- store source-tree / branch history in LangGraph checkpoints backed by PostgreSQL
- use LangGraph branching semantics as the default behavior model
- keep only the product-specific edit exceptions at application level:
  - `save`
  - `save and send`

This is the best fit for the stated principles:

- use mature frameworks when they solve the problem
- stop preserving Flutter-era storage compromises once backend frameworks provide a better path
- keep custom implementation only for product semantics that LangGraph does not define directly

