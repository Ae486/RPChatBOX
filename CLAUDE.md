# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChatBoxApp is a cross-platform Flutter LLM client application supporting multiple AI providers (OpenAI, Google, Anthropic) with advanced features like streaming output, Markdown rendering, Mermaid diagrams, and roleplay capabilities.

## Build & Development Commands

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

## Architecture

### Dependency Flow (Must Follow)
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

### Key Modules

| Directory | Purpose |
|-----------|---------|
| `lib/adapters/` | LLM API compatibility layer (OpenAI, LangChain, SSE parsing) |
| `lib/chat_ui/owui/` | OpenWebUI-compatible design system (tokens, palette, components) |
| `lib/controllers/` | Stream output timing and state control |
| `lib/models/` | Hive data models with code generation |
| `lib/models/roleplay/` | Roleplay feature models (TypeId 50-59) |
| `lib/pages/` | Route-level pages |
| `lib/rendering/` | Markdown/LaTeX/Mermaid rendering engine |
| `lib/services/` | Business logic and persistence |
| `lib/widgets/` | Reusable UI components |
| `packages/flutter_chat_ui/` | Local fork with KeyboardMixin and ChatAnimatedList fixes |

### Critical Files (Modify with Caution)

- `lib/widgets/conversation_view_v2.dart` + `lib/widgets/conversation_view_v2/*` — Main chat view (flutter_chat_ui integration + streaming)
- `lib/widgets/conversation_view_host.dart` — Chat view host (delegates to V2)
- `lib/controllers/stream_output_controller.dart` — Streaming output timing/cancellation
- `lib/adapters/*_provider.dart` — API compatibility and SSE parsing (boundary bug prone)
- `lib/services/hive_conversation_service.dart` — Persistence and data migration

## Key Design Decisions

1. **Bubble-free LLM Output**: AI responses render directly on background without bubble wrapping
2. **flutter_chat_ui Standard**: UI follows flutter_chat_ui visual patterns
3. **Local Package Fork**: `packages/flutter_chat_ui/` contains fixes for keyboard scroll and list offset tracking
4. **Roleplay Feature Layer**: Optional module with isolated storage namespace (`rp_*` Hive boxes, TypeId 50-59)

## Hive TypeId Allocation

| Range | Purpose |
|-------|---------|
| 0-3 | Core models (Conversation, Message, File) |
| 50-59 | Roleplay feature models |

## Testing

- **Unit tests**: `test/unit/` (adapters, models, services)
- **Widget tests**: `test/widgets/`
- **Golden tests**: `test/golden/` (UI snapshots with golden_toolkit)
- **Test helpers**: `test/helpers/`, `test/mocks/`

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
- `docs/roleplay-feature/` — Roleplay feature design and implementation
- `docs/ui-rearchitecture/` — UI refactoring documentation
