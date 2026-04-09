# ChatBoxApp Memory

Last Updated: 2026-04-08 (compressed canonical memory)
Maintainer: Codex Agent

## Purpose
- This file stores durable project truths, current architecture boundaries, active migration direction, and current risks.
- This file is **not** a work log. Remove obsolete or duplicated material instead of appending history.

## Persistent Rules (User Required)
- Keep this file aligned with the latest durable project understanding.
- Record only high-value facts, active constraints, real architecture status, and current priorities.
- Use explicit status labels: `implemented`, `integrated`, `not integrated`, `risk`, `next`.
- If a statement becomes wrong for the current stage, delete or rewrite it instead of preserving it as history.
- Persistent workflow requirements should also be mirrored in in-repo guidance files when appropriate.

## Core Principles
- confirmed: the original project placed most of the LLM runtime chain in Flutter; the target direction is Python backend takeover of runtime responsibilities.
- confirmed: Flutter code is a **behavior reference**, not an implementation blueprint.
- confirmed: Flutter should converge to real frontend duties only:
  - UI
  - interaction
  - streaming presentation
  - local display/cache state as needed for UX
- confirmed: Python implementation is `framework-first / wheel-first`.
  - use mature Python LLM ecosystem components before custom implementation
  - do not port Flutter-side implementations line-by-line
- confirmed: direct mode remains a rollback path until backend takeover is sufficiently complete.
- confirmed: RP should be redesigned on the Python side; existing Flutter RP code is not the target architecture.
- confirmed: MCP / tool / skill should be rebuilt around stronger Python ecosystem capabilities where appropriate; existing Flutter structure is not authoritative.
- confirmed: conversation/session should also converge to backend true-source ownership; Flutter should only keep frontend-local UX state.
- confirmed: PostgreSQL is the target primary database for backend true-source persistence.

## Project Snapshot
- stack: Flutter multi-platform client + Python FastAPI backend.
- frontend runtime entry: `lib/main.dart`
- frontend chat path:
  - `lib/widgets/conversation_view_v2/streaming.dart`
  - `lib/controllers/stream_output_controller.dart`
  - `lib/widgets/stream_manager.dart`
- frontend provider selection:
  - `lib/adapters/ai_provider.dart`
  - `pythonBackendEnabled == false` -> direct `HybridLangChainProvider`
  - `pythonBackendEnabled == true` -> `ProxyOpenAIProvider`
- backend runtime entry:
  - `backend/main.py`
  - `backend/api/chat.py`
- backend execution center:
  - `backend/services/runtime_routing_service.py`
  - `backend/services/litellm_service.py`
  - `backend/services/llm_proxy.py`
  - `backend/services/gemini_native_service.py`

## Responsibility Boundary
- Flutter should keep:
  - chat UI
  - thinking/body/tool visual presentation
  - markdown/code/latex/mermaid rendering
  - input interaction
  - local UX state
  - backend lifecycle toggle/startup entry
- backend should own:
  - upstream model execution
  - request normalization
  - provider/model runtime truth
  - routing / retry / timeout / fallback / cancel semantics
  - stream semantics normalization
  - error normalization
  - future MCP/tool/skill runtime
  - future RP/agent orchestration
- confirmed: request classes should be separated conceptually and eventually operationally:
  - control-plane: local/backend-fast metadata and health paths (`/api/health`, provider registry, model registry, settings-sync style requests)
  - data-plane: upstream-dependent requests (`/v1/chat/completions`, upstream model discovery via `POST /models`, future agent/model/tool upstream work)

## Current Architecture Status
- implemented: backend request model already supports migration-specific extensions:
  - `provider_id`
  - `model_id`
  - `stream_event_mode = legacy | typed`
  - explicit routing hints (`backend_mode`, `fallback_enabled`, `fallback_timeout_ms`, `circuit_breaker`)
- implemented: backend provider registry exists:
  - `backend/models/provider_registry.py`
  - `backend/services/provider_registry.py`
  - `backend/api/providers.py`
- implemented: backend provider-scoped model registry exists:
  - `backend/models/model_registry.py`
  - `backend/services/model_registry.py`
  - `backend/api/provider_models.py`
- implemented: backend runtime routing exists and already prefers Python-side execution policy:
  - LiteLLM primary path
  - safe httpx fallback before visible output
  - optional Gemini native path when applicable
- implemented: backend stream layer now has an internal structured event model:
  - `backend/models/stream_event.py`
  - `backend/services/stream_normalization.py`
- implemented: backend can emit both:
  - legacy `<think>`-compatible SSE
  - typed SSE payloads
- integrated: Flutter proxy requests typed SSE by default through `ProxyOpenAIProvider`.
- integrated: Flutter already has a typed consumer bridge:
  - `AIStreamEvent`
  - `StreamOutputController`
  - `conversation_view_v2/streaming.dart`
  - `StreamManager.appendThinking()`
  - `StreamManager.appendText()`
- integrated: provider/model sync and mirror refresh paths now exist in Flutter:
  - `lib/services/model_service_manager.dart`
  - `lib/pages/settings_page.dart`
  - `lib/pages/model_services_page.dart`
- implemented: frontend HTTP request isolation baseline now exists:
  - `lib/services/dio_service.dart` provides separate `controlPlaneDio` and `dataPlaneDio`
  - backend registry/provider-model sync uses control-plane client
  - proxy chat/model-discovery and direct provider traffic use data-plane client
- implemented: core chat runtime can now send `model_id` and backend resolves runtime model/provider from registry before execution.
- implemented: `ModelServiceManager` now has a unified `refreshBackendMirrors()` entry for provider/model sync + refresh bootstrap and page-level backend-first mirror updates.
- implemented: provider/model single-source slice is now backend-first for the current scope.
  - provider/model CRUD commits to backend registry first when backend mode is enabled
  - provider/model mirror refresh is backend-authoritative and removes local-only stale entries
  - conversation-level selected provider/model ids are reconciled against refreshed backend-authoritative mirrors
- implemented: backend conversation/session true-source foundation now exists.
  - `backend/config.py` resolves durable database URLs and normalizes PostgreSQL DSNs for LangGraph checkpointers
  - `backend/services/database.py` initializes SQLModel persistence
  - `backend/models/conversation_store.py` defines backend-owned conversation metadata and conversation settings records
  - `backend/services/conversation_store.py` provides backend CRUD for conversation metadata/settings
  - `backend/api/conversations.py` exposes conversation/settings CRUD endpoints
  - backend startup now initializes SQLModel tables and LangGraph PostgreSQL checkpoint schema when PostgreSQL is configured
- implemented: backend provider registry now preserves the existing stored `api_key` when an update sends a blank key for an existing provider.
  - this allows Flutter to keep a blank local mirror for backend-held secrets without clobbering the backend secret on edit
- integrated: provider detail editing now preserves existing routing/proxy fields and supports backend-secret-preserving edits for existing providers.
- confirmed: assessment for the core LLM communication chain is:
  - backend takeover is functionally mostly complete for the basic chat/request/stream execution path
  - provider/model single-source is mostly complete for the current migration scope
  - but it is not yet the final backend-only single-source runtime boundary because conversation/session/MCP/RP runtime truth is still not backend-owned

## Current Non-Final Boundaries
- not integrated: backend is not yet the final single source of truth.
  - Flutter still keeps local provider/model mirrors as UI cache / rollback layer
- not integrated: Flutter provider instantiation still uses the global backend switch; provider-level routing is not yet the frontend-side source of truth.
- not integrated: backend does not yet own full conversation/session storage.
- not integrated: backend now owns conversation metadata/settings foundation, but Flutter conversation/session read-write flow has not yet cut over to it.
- not integrated: source message tree / visible-chain read models are not yet backed by LangGraph checkpoints in the production flow.
- not integrated: backend does not yet own full MCP runtime/tool execution loop.
- not integrated: backend does not yet provide the redesigned RP runtime.
- not integrated: current typed-stream work is foundation work, not the final tool/MCP/RP runtime.
- not integrated: there is no real multi-agent backend orchestration/runtime yet.
  - current conversation UI is still single-active-stream oriented
  - future multi-agent parallel work must be designed as backend-side concurrency, not Flutter-side orchestration

## RP / MCP Reset
- confirmed: existing Flutter RP code may be treated as an exploratory shell, not a target implementation.
- confirmed: existing Flutter MCP/tool path may be treated as an exploratory shell, not a target implementation.
- confirmed: future RP work should start from backend-side design, not from preserving current Flutter internals.
- confirmed: future MCP/tool/skill work should prefer Python ecosystem frameworks and server-side policy enforcement.
- implication: when evaluating old Flutter subsystems, preserve user-visible behavior only when it is still product-relevant; do not preserve internal structure by default.
- confirmed: intended RP architecture is layered-agent orchestration on the backend:
  - top-layer model decides which specialized sub-agents to activate
  - specialized sub-agents perform focused work such as body generation, memory compression, foreshadow evaluation/recall, inventory/item management
  - user-facing primary foreground result is body output
  - non-body maintenance work should run asynchronously in the background
  - backend should expose corresponding state/read models so Flutter can offer dedicated UI entry points such as memory management and item management

## Current Risks
- resolved: attachment handling now supports remote upload via base64 `data` field in addition to local file path. `AttachedFile.data` carries base64-encoded content; `path` is optional fallback for co-located desktop backend. Flutter reads file bytes and encodes base64 before sending to backend.
- risk: some migration docs lag behind the now-landed code, especially around typed-stream bridge and model-registry progress.
- risk: current migration can still be misframed if Flutter implementation details are treated as authoritative architecture.
- risk: current frontend request isolation is weak.
  - baseline split is now implemented, but this is only first-layer isolation
  - future agent/runtime stages may still need stronger separation across foreground chat, background agent tasks, and control-plane reads/writes

## Verification Baseline
- implemented: backend has targeted tests around chat API, routing, stream normalization, provider registry, and model registry.
- implemented: Flutter has targeted tests around proxy parsing, stream controller/state, request characterization, and model service sync.
- confirmed: changes touching the chat pipeline should continue to verify both backend and Flutter targeted suites.

## Current Priority
- next: continue backend takeover of runtime truth and execution semantics; do not drift back into Flutter-side runtime logic.
- next: provider/model current-scope single-source is in place; continue tightening the remaining runtime boundaries beyond this slice.
- next: build LangGraph-backed source-thread persistence and backend visible-chain read models on top of the new conversation metadata foundation.
- next: keep frontend rendering behavior stable while moving semantics/control into backend.
- next: design Python-first replacements for MCP/tool/skill and RP instead of extending current Flutter subsystems.
- confirmed: future conversation/source tree should follow LangGraph branching/checkpoint semantics rather than preserving the current Flutter tree implementation as the target architecture.
- confirmed: regenerate and branch navigation should follow LangGraph-style branch semantics.
- confirmed: current Flutter-specific tree rewiring behaviors are not target architecture by default.
- confirmed: the current Flutter conversation storage bundle (`threadJson + activeLeafId + messages snapshot + messageIds + messageBox`) should not be carried forward as backend truth.
  - necessary foundation is: durable source-tree / checkpoint lineage, selected branch pointer, message revision capability, and backend read models for current visible chain
  - current `conversation.messages` active snapshot, duplicate `activeLeafId`, `messageIds`, and message lookup pass-through are Flutter/Hive-era storage compromises rather than required future foundation
  - this does not invalidate future rollback requirements; source rollback can be built on LangGraph checkpoints, while wider RP multi-scope rollback still needs app-level Snapshot/Head/Operation semantics on top
- confirmed: PostgreSQL + LangGraph is the target backend true-source split for conversation/session migration.
  - PostgreSQL app tables should own stable business data such as conversation metadata, settings, summaries, and attachment metadata
  - LangGraph checkpoints should own source-tree / branch / checkpoint history
- implemented: current backend migration foundation already follows that split direction without reproducing Flutter's tree/snapshot duplication.
  - SQLModel/PostgreSQL-side foundation currently owns conversation metadata and generation-affecting settings
  - LangGraph PostgreSQL checkpoint schema is initialized when PostgreSQL is configured
  - source-tree checkpoint read/write integration is still pending
- confirmed: current Flutter conversation persistence has redundant truth layers:
  - `threadJson`
  - `activeLeafId`
  - `conversation.messages` active-chain snapshot
  - `messageIds`
  - separate message box lookup path
  These should not be reproduced as backend source-of-truth storage.
- confirmed: `save` edit mode should remain as product behavior, but should be implemented as application-layer state patching on top of LangGraph-style persistence rather than preserving the Flutter tree engine.
- confirmed: local historical conversation data can be discarded during backend cutover; provider/model data must be retained.
- next: do not defer all concurrency/isolation work until full RP-agent phase.
  - immediate foundation work is justified where it prevents known UX coupling or obvious future rework
  - especially separate control-plane and data-plane request/client paths
  - full async multi-agent runtime can wait, but request isolation should not
- next: for layered RP agents, plan around:
  - LiteLLM as provider gateway/runtime compatibility layer
  - PydanticAI for typed agent/tool/output workflows
  - LangGraph only if graph-style multi-agent orchestration/checkpointing becomes the dominant complexity
  - a durable workflow/runtime layer (for example Temporal-class tooling) once background maintenance jobs must survive request lifetimes and process restarts
  - project-specific RP domain schema, trigger policy, merge/apply policy, and UI read models remaining custom responsibilities

## Key References
- `docs/migration/07-backend-architecture-and-tech-selection.md`
- `docs/migration/08-migration-execution-plan.md`
- `docs/migration/10-typed-stream-review-and-plan.md`
- `docs/migration/11-typed-stream-schema.md`
- `docs/migration/12-provider-model-single-source-plan.md`
