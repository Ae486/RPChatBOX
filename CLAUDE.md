# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChatBoxApp is a cross-platform Flutter LLM client application with Python backend proxy, supporting multiple AI providers (OpenAI, Google, Anthropic) with advanced features like streaming output, Markdown rendering, Mermaid diagrams, and roleplay capabilities.

## Build & Development Commands

### Flutter Client

```bash
# Install dependencies
flutter pub get

# Run the app (debug mode)
flutter run

# Run on specific platform
flutter run -d windows
flutter run -d chrome
flutter run -d android

# Build for production
flutter build windows
flutter build apk
flutter build web

# Generate Hive adapters (required after modifying @HiveType models)
flutter pub run build_runner build --delete-conflicting-outputs

# Watch mode for code generation
flutter pub run build_runner watch

# Run all tests
flutter test

# Run specific test directory
flutter test test/unit/
flutter test test/golden/

# Run tests with coverage
flutter test --coverage

# Analyze code
flutter analyze
```

### Python Backend

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (first time)
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Run development server (with auto-reload)
python main.py
# Or with uvicorn directly
uvicorn main:app --host 127.0.0.1 --port 8765 --reload

# Run tests
pytest

# API docs (debug mode only)
# http://localhost:8765/docs (Swagger UI)
# http://localhost:8765/redoc (ReDoc)
```

## Architecture

### Overall Architecture
```
┌──────────────────────────────────────────────────────┐
│                    Flutter App                        │
│  UI → Provider → Controller → Service → Adapter      │
│                                           │          │
│                    RoutingProviderFactory              │
│                    (backendMode: direct|proxy|auto)   │
│                     ┌──────────┴──────────┐           │
│              DirectProvider         ProxyProvider      │
│              (existing)          (localhost:8765)      │
└──────────────┼──────────────────────┼────────────────┘
               │ HTTPS           HTTP │
               ▼                      ▼
          ┌─────────┐     ┌───────────────────┐
          │ LLM APIs│     │  Python Backend   │
          └─────────┘     │  (FastAPI proxy)  │
                          └────────┬──────────┘
                                   │ HTTPS
                                   ▼
                              ┌─────────┐
                              │ LLM APIs│
                              └─────────┘
```

### Flutter Client Dependency Flow (Must Follow)
```
UI (lib/pages + lib/widgets + lib/chat_ui/owui)
    ↓
State Management (Provider: lib/providers)
    ↓
Controllers (lib/controllers)
    ↓
Business Services (lib/services)
    ↓
Provider Adapters (lib/adapters)
    ↓
Data Models (lib/models) + Hive Storage
```

### Key Modules — Flutter Client

| Directory | Purpose |
|-----------|---------|
| `lib/adapters/` | LLM API compatibility layer (OpenAI, LangChain, Proxy, Routing) |
| `lib/adapters/proxy_openai_provider.dart` | Routes requests to Python backend proxy |
| `lib/adapters/backend_routing_provider.dart` | Auto-mode: proxy with fallback to direct |
| `lib/chat_ui/owui/` | OpenWebUI-compatible design system (tokens, palette, components) |
| `lib/controllers/` | Stream output timing and state control |
| `lib/models/` | Hive data models with code generation |
| `lib/models/backend_mode.dart` | BackendMode enum (direct/proxy/auto) |
| `lib/models/circuit_breaker_config.dart` | Circuit breaker configuration model |
| `lib/models/roleplay/` | Roleplay feature models (TypeId 50-59) |
| `lib/pages/` | Route-level pages |
| `lib/rendering/` | Markdown/LaTeX/Mermaid rendering engine |
| `lib/services/` | Business logic and persistence |
| `lib/services/circuit_breaker_service.dart` | Circuit breaker state machine |
| `lib/services/fallback_policy.dart` | Proxy→direct fallback decision logic |
| `lib/widgets/` | Reusable UI components |
| `packages/flutter_chat_ui/` | Local fork with KeyboardMixin and ChatAnimatedList fixes |

### Key Modules — Python Backend (`backend/`)

| File/Directory | Purpose |
|----------------|---------|
| `backend/main.py` | FastAPI entry point, CORS, startup |
| `backend/config.py` | Settings with `CHATBOX_BACKEND_` env prefix |
| `backend/api/chat.py` | `/v1/chat/completions` and `/models` endpoints |
| `backend/api/health.py` | `/api/health` endpoint |
| `backend/models/chat.py` | Pydantic request/response models |
| `backend/services/llm_proxy.py` | LLM proxy service (upstream forwarding + SSE relay) |
| `backend/tests/` | pytest test suite |

### Critical Files (Modify with Caution)

- `lib/widgets/conversation_view_v2.dart` + `lib/widgets/conversation_view_v2/*` — Main chat view (flutter_chat_ui integration + streaming)
- `lib/widgets/conversation_view_host.dart` — Chat view host (delegates to V2)
- `lib/controllers/stream_output_controller.dart` — Streaming output timing/cancellation
- `lib/adapters/*_provider.dart` — API compatibility and SSE parsing (boundary bug prone)
- `lib/adapters/backend_routing_provider.dart` — Proxy/direct routing with circuit breaker
- `lib/services/hive_conversation_service.dart` — Persistence and data migration
- `backend/services/llm_proxy.py` — SSE streaming relay (must comply with SSE constraints)

## Key Design Decisions

1. **Bubble-free LLM Output**: AI responses render directly on background without bubble wrapping
2. **flutter_chat_ui Standard**: UI follows flutter_chat_ui visual patterns
3. **Local Package Fork**: `packages/flutter_chat_ui/` contains fixes for keyboard scroll and list offset tracking
4. **Roleplay Feature Layer**: Optional module with isolated storage namespace (`rp_*` Hive boxes, TypeId 50-59)
5. **Backend Routing**: LLM requests support three modes (direct/proxy/auto) via `BackendMode`
6. **Fallback Strategy**: Auto mode uses proxy-first with circuit breaker for automatic fallback to direct

## Backend Mode Configuration

| Mode | Behavior |
|------|----------|
| `direct` | Connect directly to LLM API (default, existing behavior) |
| `proxy` | Route through Python backend (`http://localhost:8765`) |
| `auto` | Prefer proxy, fallback to direct on failure (circuit breaker enabled) |

### ProviderConfig Extensions for Backend

- `backendMode`: BackendMode (direct/proxy/auto)
- `proxyApiUrl`: Optional proxy URL (default: `http://localhost:8765`)
- `proxyApiKey`: Optional separate auth for proxy
- `proxyHeaders`: Optional proxy-specific headers
- `fallbackEnabled`: Enable fallback in auto mode (default: true)
- `circuitBreaker`: CircuitBreakerConfig (failure threshold, timing)

## Backend API Contract

Backend implements OpenAI-compatible endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/v1/chat/completions` | POST | Chat completions (streaming/non-streaming) |
| `/models` or `/v1/models` | GET/POST | List models |

### SSE Streaming Constraints (Critical)

- Each event: `data: {json}\n\n` format
- JSON must not span multiple lines (LineSplitter limitation)
- Stream ends with `data: [DONE]\n\n`
- Headers: `Content-Type: text/event-stream`, `X-Accel-Buffering: no`
- No buffering, immediate flush per chunk

## Hive TypeId Allocation

| Range | Purpose |
|-------|---------|
| 0-3 | Core models (Conversation, Message, File) |
| 50-59 | Roleplay feature models |

## Testing

### Flutter Client
- **Unit tests**: `test/unit/` (adapters, models, services)
- **Widget tests**: `test/widgets/`
- **Golden tests**: `test/golden/` (UI snapshots with golden_toolkit)
- **Test helpers**: `test/helpers/`, `test/mocks/`

### Python Backend
- **Location**: `backend/tests/`
- **Framework**: pytest + pytest-asyncio
- **Run**: `cd backend && pytest`

## Platform Support

All platforms supported: Android, iOS, Windows, macOS, Linux, Web

Windows-specific: WebView2 requires manual initialization (handled in `main.dart`)

## Maintenance Rules

1. After modifying a file → Update file header comments (INPUT/OUTPUT/POS if applicable)
2. After modifying a directory → Update directory's `INDEX.md` if present
3. Cross-module changes → Update root `README.md`
4. Roleplay feature → Extend, don't modify base layer code

## Specs & Documentation

- `specs/chat-storage/CHAT_STORAGE_PRO_SPEC.md` — Storage specification
- `specs/ui-rearchitecture/` — UI component specifications
- `specs/llm-backend-migration/` — Backend migration specification and constraints
  - `CONSTRAINT_SET.md` — API contract, SSE format, fallback rules
  - `IMPLEMENTATION_PLAN.md` — Phase-by-phase implementation plan
- `docs/roleplay-feature/` — Roleplay feature design and implementation
- `docs/ui-rearchitecture/` — UI refactoring documentation

## Environment Variables

### Python Backend (`CHATBOX_BACKEND_` prefix)

| Variable | Default | Description |
|----------|---------|-------------|
| `CHATBOX_BACKEND_HOST` | `127.0.0.1` | Server bind address |
| `CHATBOX_BACKEND_PORT` | `8765` | Server port |
| `CHATBOX_BACKEND_DEBUG` | `false` | Enable debug mode (docs, reload) |
| `CHATBOX_BACKEND_LLM_REQUEST_TIMEOUT` | `120.0` | Upstream request timeout (seconds) |
| `CHATBOX_BACKEND_LLM_CONNECT_TIMEOUT` | `30.0` | Upstream connect timeout (seconds) |
