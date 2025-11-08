# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Development Commands

### Essential Commands
```powershell
# Install dependencies
flutter pub get

# Run on Windows
flutter run -d windows

# Run on Android (check available devices first)
flutter devices
flutter run -d <device-id>

# Run static analysis
flutter analyze

# Run tests
flutter test
```

### Build Commands
```powershell
# Build for Windows
flutter build windows

# Build for Android
flutter build apk
flutter build appbundle

# Build for Web
flutter build web
```

## Project Architecture

### Core Architecture Pattern: IndexedStack + AutomaticKeepAliveClientMixin

This application uses a sophisticated **IndexedStack-based multi-conversation management system** that preserves state perfectly when switching between conversations:

**Key Design:**
- `ChatPage` manages a list of `Conversation` objects and uses `IndexedStack` to display them
- Each conversation has its own `ConversationView` widget with `AutomaticKeepAliveClientMixin`
- Each `ConversationView` maintains independent state: scroll position, input text, loading state, edit mode
- Switching conversations is instant (<16ms) with zero rebuilds or data loss

**Critical Implementation Details:**
```dart
// ChatPage uses IndexedStack
IndexedStack(
  index: _currentIndex,
  children: _conversations.map((conv) =>
    ConversationView(
      key: GlobalKey<ConversationViewState>(),
      conversation: conv,
      // Each view maintains its own state
    )
  ).toList(),
)

// ConversationView preserves state
class _ConversationViewState extends State<ConversationView>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true; // Critical!
}
```

**Why This Matters:** When editing code related to conversation switching, state management, or UI updates, you MUST understand that:
1. Each conversation view stays alive even when not visible
2. State is never recreated on switch
3. Scroll positions, input text, and UI state are preserved per-conversation
4. Changes to one conversation's state should not affect others

### Streaming Response Architecture

The app uses **Server-Sent Events (SSE)** for real-time AI responses:

**Flow:**
1. User sends message → `ConversationView._sendMessage()`
2. Creates a streaming request via `AIProvider.sendMessageStream()`
3. Response arrives in chunks via SSE format: `data: {"choices":[{"delta":{"content":"..."}}]}`
4. Each chunk is yielded through a Dart `Stream<String>`
5. UI updates in real-time using `StreamBuilder` or stream subscription
6. `EnhancedStreamController` manages the streaming state

**Key Files:**
- `lib/services/openai_service.dart` - Legacy streaming implementation
- `lib/adapters/openai_provider.dart` - Current provider pattern
- `lib/controllers/stream_output_controller.dart` - Stream state management

### Provider-Model Architecture (v3.4.0+)

The app has migrated from a single `ChatSettings` to a **multi-provider, multi-model architecture**:

**Components:**
- `ProviderConfig` - Represents an AI service (OpenAI, Claude, Gemini, DeepSeek, Custom)
- `ModelConfig` - Represents a specific model (gpt-4, claude-3-opus, etc.)
- `ConversationSettings` - Per-conversation configuration (which model to use, parameters, attachments)
- `ModelServiceManager` - Central manager for CRUD operations and persistence

**Migration System:**
- `ConfigMigration` automatically migrates from old `ChatSettings` format
- Migration occurs on first launch after upgrade
- Old settings are preserved in `chat_settings` key for rollback

**Key Files:**
- `lib/services/model_service_manager.dart` - Central management
- `lib/models/provider_config.dart` - Provider definitions
- `lib/models/model_config.dart` - Model definitions
- `lib/models/config_migration.dart` - Migration logic
- `lib/adapters/ai_provider.dart` - Abstract provider interface

### Attachment System (v3.4.0+)

**Design Philosophy:** Lightweight snapshots, not file duplication

- `AttachedFile` - Temporary file object during composition (in-memory)
- `AttachedFileSnapshot` - Persistent reference saved with message (path + metadata only)
- Files are NOT copied; only paths are stored
- Graceful degradation: if file is deleted, show placeholder instead of crashing

**Image Attachments:**
- Thumbnails shown in message bubbles
- Click to open full-screen viewer with zoom/pan (`photo_view` package)
- Base64-encoded for API transmission

**Document Attachments:**
- File content read and sent to AI as context
- Displayed as clickable cards in message bubbles

**Key Files:**
- `lib/models/attached_file.dart` - File models
- `lib/services/file_content_service.dart` - File reading logic
- `lib/widgets/conversation_view.dart` - Attachment UI rendering

## Code Structure & Patterns

### Layer Separation

```
lib/
├── main.dart              # App entry, theme management, global instances
├── models/                # Pure data classes (JSON serialization)
├── services/              # Business logic (API calls, storage, state management)
├── adapters/              # Provider abstraction layer
├── controllers/           # Stream/state controllers
├── pages/                 # Full-screen views
├── widgets/               # Reusable UI components
└── utils/                 # Pure functions (token counting, content detection)
```

### State Management Pattern

This app uses **StatefulWidget + setState** (no Provider/Bloc/Riverpod):
- Global state: `globalModelServiceManager` singleton (initialized in `main.dart`)
- Per-conversation state: Managed by `ConversationViewState`
- Persistence: `SharedPreferences` via `StorageService`
- Callbacks: Parent widgets pass `VoidCallback` and `Function(T)` to children for state updates

### Rendering Pipeline

**Complex Content Rendering:**
1. `EnhancedContentRenderer` - Main coordinator
2. Detects content type: plain text, Markdown, LaTeX, Mermaid, code
3. Routes to specialized renderers:
   - `flutter_markdown` - Basic Markdown
   - `flutter_math_fork` - LaTeX equations
   - `MermaidRenderer` - Mermaid diagrams (WebView-based)
   - `flutter_highlight` - Code syntax highlighting

**WebView Usage:**
- Used for Mermaid diagrams and complex LaTeX
- Platform-specific initialization (handled automatically on Windows/Android)
- HTML templates loaded from `assets/web/`

### Scroll Position Management

**ItemScrollController Pattern:**
- Uses `scrollable_positioned_list` package, not standard `ScrollController`
- Allows jumping to arbitrary indices without building all intermediate items
- Each conversation stores `scrollIndex` (int) representing first visible message
- Auto-saves scroll position every 500ms during scrolling
- Restores position on conversation switch via `_restoreScrollPosition()`

**Smart Auto-Scroll:**
- Only scrolls to bottom during streaming if user is near bottom (`_isUserNearBottom`)
- Detects user scrolling via `_markUserScrolling()` and temporarily disables auto-scroll
- Debounced scroll detection (1 second) prevents false positives

## Common Development Patterns

### Adding a New AI Provider

1. Create provider class extending `AIProvider` in `lib/adapters/`
2. Implement required methods: `testConnection()`, `sendMessageStream()`, `listAvailableModels()`
3. Add provider type to `ProviderType` enum in `lib/models/provider_config.dart`
4. Register in `ProviderFactory.createProvider()` switch statement
5. Update UI in `lib/pages/model_services_page.dart` for provider-specific configuration

### Adding a New Content Renderer

1. Create widget in `lib/widgets/` (e.g., `my_renderer.dart`)
2. Add detection logic in `lib/utils/content_detector.dart`
3. Integrate into `EnhancedContentRenderer` routing logic
4. Test with various content types to avoid false positives

### Modifying Conversation State

**Always use this pattern:**
```dart
setState(() {
  // Modify conversation or local state
  widget.conversation.messages.add(newMessage);
});

// Trigger parent update for persistence
widget.onConversationUpdated();
```

**Never directly mutate without setState** - Flutter won't rebuild the UI.

## Testing

### Test Structure
- `test/widget_test.dart` - Basic widget tests
- `lib/test/latex_test_examples.dart` - LaTeX rendering test cases
- `lib/pages/latex_test_page.dart` - Manual LaTeX testing UI

### Running Tests
```powershell
flutter test                    # All tests
flutter test test/widget_test.dart  # Specific file
```

## Important Technical Constraints

### Windows Platform
- WebView support is automatic (uses Edge WebView2)
- File paths use Windows-style backslashes
- No additional platform configuration needed for WebView

### Message Persistence
- Messages include `AttachedFileSnapshot` list (not just IDs)
- Snapshots are lightweight (path + metadata, not file content)
- Always check file existence before rendering attachments

### Token Counting
- Approximate counting using character-based heuristics (1 token ≈ 4 chars)
- Not 100% accurate but good enough for cost estimation
- Real token count only available from API response

### Streaming State
- Must handle incomplete JSON during streaming
- Parser errors in chunks should be silently ignored (common with SSE)
- Always check for `[DONE]` marker to properly close stream

## Multi-Language Support (Chinese Primary)

This codebase is primarily documented in Chinese:
- UI strings are in Chinese
- Comments are mostly in Chinese
- README and CHANGELOG are in Chinese
- User-facing error messages are in Chinese

When adding features, maintain consistency with existing language usage.
