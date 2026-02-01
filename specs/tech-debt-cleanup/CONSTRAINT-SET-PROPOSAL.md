# Technical Debt Cleanup - Constraint Set Proposal

> Created: 2026-02-01
> Status: Draft (Pending Approval)
> Analysis Source: Codex (019c186d-d756-7f62-9e08-f5ad533755aa) + Gemini (315c9d3f-aa25-424b-9315-ab0ce8377d56)
> Audit Reference: docs/analyze/SUMMARY.md

---

## Executive Summary

Based on comprehensive code quality audit (~45,000 lines), this proposal defines implementation constraints for fixing **8 Critical** and **20+ High Priority** issues across the ChatBoxApp codebase.

### Issue Distribution

| Priority | Count | Impact |
|----------|-------|--------|
| P0 (Critical) | 8 | App crash, streaming failure, yellow screen |
| P1 (High) | 12 | Performance degradation, resource leaks |
| P2 (Medium) | 10+ | Maintainability, code quality |

---

## P0 Constraint Sets (Week 1 - Must Fix)

### CS-01: Rendering State Machine Stabilization

**Priority:** P0
**Issues:** C1 (Fence 4+ backtick), C2 (Table lock), C3 (HTML stack), C4 (HTML gating)
**Location:** `lib/rendering/markdown_stream/stable_prefix_parser.dart`

**Dependencies:**
- C4 must be fixed before C1/C2/C3 (gate fence/table detection while in HTML)
- Add parser invariants before logic tweaks

**Architectural Pattern:** Explicit state machine + guard clauses; HTML stack discipline

**Implementation Constraints:**
1. Do NOT change output format for previously valid markdown cases
2. Ensure HTML block state fully gates fence/table detection
3. Track HTML open/close on the same line and pop correctly
4. Avoid adding allocations in hot parsing loops
5. Support 4+ backtick fences per CommonMark spec
6. Single-pipe rows must NOT lock tableMode indefinitely

**Tests Required:**
- Unit tests for parser state transitions (each state × input combination)
- Streaming incremental tests (partial chunks)
- Golden render tests for fences/tables/HTML
- Regression cases: 4+ backticks, one-line HTML tags, single-pipe rows

**Risk:** Markdown rendering regressions; subtle streaming stalls

---

### CS-02: Provider Crash Prevention

**Priority:** P0
**Issues:** C5 (DeepSeek/Claude UnimplementedError)
**Location:** `lib/adapters/ai_provider.dart:206,221,262`

**Dependencies:** None; must land before any new provider UX work

**Architectural Pattern:** Factory + Strategy with safe fallback; explicit "unsupported" error path

**Implementation Constraints:**
1. NEVER throw `UnimplementedError` from UI-reachable code
2. Provide deterministic error message for unsupported providers
3. Preserve existing provider IDs and config schema
4. Route DeepSeek → OpenAI-compatible endpoint (if API compatible)
5. Route Claude → dedicated Anthropic adapter OR clear "not supported" message

**Tests Required:**
- Unit tests for provider factory selection (all ProviderType enum values)
- Widget tests for provider selection UI
- Integration test selecting each provider type

**Risk:** Incorrect provider routing; degraded error messaging

---

### CS-03: Initialization & Lifecycle Safety

**Priority:** P0
**Issues:** C6 (async init timing), C7 (Uri.tryParse crash), C8 (setState after dispose)
**Locations:**
- `lib/providers/chat_session_provider.dart:32-34`
- `lib/pages/provider_detail_page.dart:366`
- `lib/pages/*.dart`, `lib/widgets/*.dart` (multiple)

**Dependencies:**
- C6 before any tests that touch chat/session storage
- C8 fixes before performance refactors that add async work

**Architectural Pattern:**
- Async init barrier + ready flag
- Dispose guards (`mounted` checks)
- Safe URL parsing with validation

**Implementation Constraints:**
1. Public methods MUST short-circuit or await init completion
2. All async UI updates MUST check `mounted` before `setState`:
   ```dart
   await someAsyncOperation();
   if (!mounted) return;
   setState(() { ... });
   ```
3. URL parsing MUST handle invalid input without throwing:
   ```dart
   final uri = Uri.tryParse(value);
   if (uri == null) { /* handle error */ }
   ```
4. Add `_disposed` guard flag to ChatSessionProvider
5. Implement proper `dispose()` that calls `_conversationService.close()`

**Tests Required:**
- Unit tests for init gating (public methods before/after init)
- Widget tests for fast navigation (quick push/pop)
- Integration test with invalid URL input
- Lifecycle regression tests

**Risk:** Deadlocks if init gating is wrong; missed UI updates

---

### CS-04: Dialog Controller Lifecycle

**Priority:** P0
**Issues:** U2 (TextEditingController leak in dialogs)
**Locations:** `chat_page:72`, `custom_roles_page:69`

**Architectural Pattern:** Scoped controller ownership

**Implementation Constraints:**
1. NEVER instantiate `TextEditingController` directly in `showDialog` builder
2. Either:
   - Use `TextFormField(initialValue:)` instead of controller
   - OR manage controller in parent StatefulWidget with proper dispose
   - OR use `OwuiDialog` wrapper that handles controller lifecycle
3. Timers and AnimationControllers MUST be cancelled in `dispose()`

**Tests Required:**
- Widget tests verifying no "setState after dispose" errors
- Memory leak tests (open/close dialog repeatedly)

**Risk:** Lost state on navigation

---

## P1 Constraint Sets (Week 2 - High Priority)

### CS-05: Performance Hotspots

**Priority:** P1
**Issues:** Base64 decode in build(), sync code highlight, ChunkBuffer O(n²)
**Dependencies:** P0 stability fixes completed

**Architectural Pattern:** Caching/memoization; lazy decode; async/isolate processing

**Implementation Constraints:**
1. NEVER call `base64Decode` in `build()` method
2. Use `compute()` for heavy decoding OR `MemoryImage` with `cacheWidth`/`cacheHeight`
3. Code highlighting MUST be async or use isolate for long blocks
4. Replace string concatenation with `StringBuffer` in ChunkBuffer
5. Cache keys must include all inputs (theme, language, text hash)

**Tests Required:**
- Micro-benchmarks for decode/highlight
- Widget performance tests (scroll FPS)
- Unit tests for ChunkBuffer correctness

**Risk:** Visual lag from scheduling; cache invalidation bugs

---

### CS-06: Resource Leak Cleanup

**Priority:** P1
**Issues:** ChatSessionProvider no dispose(), toast timer leak
**Dependencies:** P0 lifecycle safety fixes

**Architectural Pattern:** Disposable ownership model; timer cancellation on dispose

**Implementation Constraints:**
1. Ownership of controllers/timers MUST be explicit
2. No disposal in build paths; only lifecycle hooks
3. Add null-safe checks before cancelling timers
4. ChatSessionProvider MUST call `_conversationService.close()` in dispose
5. Toast utility MUST cancel previous timer before starting new one

**Tests Required:**
- Widget tests for dispose calls
- Leak regression tests using debug flags

**Risk:** Timers cancelled too aggressively; missed cleanup in edge paths

---

### CS-07: Widget Decomposition

**Priority:** P1
**Issues:** M1 (provider_detail 845 lines), M2 (streaming 972 lines), M3 (assistant_message 600 lines)

**Architectural Pattern:** Composition over Inheritance; Part-of files

**Implementation Constraints:**
1. **provider_detail_page.dart** → Split into:
   - `ProviderFormSection` (basic info)
   - `ProviderModelsSection` (model list)
   - `ProviderTestPanel` (connection test)
2. **streaming.dart** → Separate UI from state management:
   - `StreamOutputController` as single source of truth
   - UI components only listen to `ValueListenable`
3. **assistant_message.dart** → Extract renderers:
   - Markdown, code block, Mermaid as independent stateless widgets
   - Use `const` constructors for optimization
4. Keep external interfaces stable during splits

**Tests Required:**
- Integration tests for navigation and data flow
- Regression tests for existing functionality

**Risk:** Behavior changes from refactor; API breaks

---

### CS-08: Test Strategy for UI Components

**Priority:** P1
**Issues:** General test coverage gaps

**Implementation Constraints:**
1. **Lifecycle Bug Regression:** Widget tests simulating fast back-button navigation
2. **Production Gate (U4):** Verify `KeyboardTestPage` hidden in `kReleaseMode`
3. **Golden Testing:** Establish baseline for `lib/chat_ui/owui/` components
4. **StablePrefixParser:** Comprehensive unit test suite (currently zero tests)

**Tests Required:**
- Widget tests: lifecycle, navigation
- Golden tests: OWUI components
- Unit tests: parser, adapters, services
- Integration tests: end-to-end flows

---

## P2 Constraint Sets (Week 3+ - Maintainability)

### CS-09: UI Consistency Migration (AlertDialog → OwuiDialog)

**Priority:** P2
**Issues:** U3 (mixed AlertDialog/OwuiDialog)

**Implementation Constraints:**
1. Prohibit direct `showDialog` with `AlertDialog` in business code
2. **Pilot Page:** `model_services_page.dart` as first migration target
3. Add lint rule: new code in `lib/chat_ui/owui/` must use `owui_` prefixed components
4. Create `OwuiConfirmDialog`, `OwuiInputDialog` wrappers

**Tests Required:**
- Golden tests comparing OwuiDialog against design specs

**Risk:** Low - incremental migration

---

### CS-10: Code Quality Improvements

**Priority:** P2
**Issues:** 40+ silent catch blocks, ApiError duplication, metadata handling duplication

**Implementation Constraints:**
1. Replace silent `catch(_)` with logged/typed errors
2. Migrate to single `ApiError` class (use models/ version, remove adapters/ duplicate)
3. Extract metadata handling to shared helper
4. Keep external interfaces stable during refactors
5. Gate `KeyboardTestPage` with `kDebugMode`

**Tests Required:**
- Unit tests for error mapping
- Static analysis rules (lints)

**Risk:** Behavior changes from refactor

---

## Implementation Dependency Graph

```
CS-04 (Dialog Controller) ─┐
                           │
CS-03 (Lifecycle Safety) ──┼──► CS-05 (Performance)
                           │        │
CS-02 (Provider Crash) ────┤        ▼
                           │   CS-06 (Resource Leak)
CS-01 (State Machine) ─────┘        │
                                    ▼
                              CS-07 (Decomposition)
                                    │
                                    ▼
                              CS-08 (Test Strategy)
                                    │
                              ┌─────┴─────┐
                              ▼           ▼
                        CS-09 (UI)   CS-10 (Quality)
```

---

## Success Criteria

| Phase | Criteria | Verification |
|-------|----------|--------------|
| P0 Complete | Zero crash on provider selection, valid streaming, no yellow screen | Manual QA + Automated tests |
| P1 Complete | Smooth 60fps scroll, no memory leaks on dialog, all tests pass | Performance profiling + Leak tests |
| P2 Complete | Consistent UI, <500 line files, zero silent catch | Static analysis + Code review |

---

## Next Steps

1. [ ] Review and approve this constraint set proposal
2. [ ] Create tracking issues for each CS-XX
3. [ ] Begin CS-01 through CS-04 in parallel (P0 week)
4. [ ] Daily sync on P0 progress

---

**Approval Required From:** [Project Lead]
