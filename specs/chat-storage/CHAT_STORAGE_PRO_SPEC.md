# Chat Storage Professionalization Spec (Base Chat)

> Created: 2026-01-16
> Status: Draft (Phase 3)
> Scope: Base chat only (roleplay is out-of-scope for storage logic).

---

## 0. Goals
- Make base chat storage closer to professional systems (message tree + stable IDs + summary metadata).
- Preserve existing UI behavior and data compatibility.
- Reduce later roleplay integration pressure by standardizing the message tree shape.

## 1. Non-goals
- Do NOT implement roleplay memory blocks, proposals, snapshots, or agent state here.
- Do NOT change UI behavior or feature parity in this phase.
- Do NOT ship summary UI yet (summary is backend-only triggerable).

## 2. Current State (Summary)
- `Conversation.messages` is both UI list and historical source-of-truth.
- `threadJson` stores a full conversation tree, but messages do not carry `parentId`.
- Context truncation is by message count (`contextLength`).
- Hive persistence rewrites full conversation list on save.

## 3. Proposed Data Model (Phase 0/1)
### 3.1 Message (base)
Add fields:
- `parentId: String?`  (tree parent pointer)
- `editedAt: DateTime?` (optional metadata; no behavior change)

### 3.2 Conversation (base)
Add fields:
- `activeLeafId: String?`
- `summary: String?`
- `summaryRangeStartId: String?`
- `summaryRangeEndId: String?`
- `summaryUpdatedAt: DateTime?`

### 3.3 Storage semantics (initial)
- `threadJson` remains the canonical tree **for now**.
- `parentId` is written alongside thread updates for forward compatibility.
- `Conversation.messages` remains the active-chain snapshot used by UI.

## 4. Implementation Phases
### Phase 0 (safe schema extension)
- Add fields to `Message` and `Conversation`.
- Update JSON + Hive adapters.
- No behavioral change.

### Phase 1 (dual-write parentId)
- When adding messages to the thread, write `message.parentId`.
- When loading from threadJson or linear list, backfill `message.parentId` if empty.
- Mirror `Conversation.activeLeafId` from thread state when persisting.

### Phase 2 (in-scope)
- Use `parentId` as the authoritative link when building/normalizing the tree.
- `threadJson` remains persisted but can be treated as a cache when absent/invalid.
- Provide a backend-only summary command that summarizes the active chain within current `contextLength`.
### Phase 3 (in-scope)
- Add `messageIds: List<String>` to `Conversation` as the persistent message index.
- Store `Message` objects in a dedicated Hive box (`messages`).
- Persist conversations **without** the `messages` payload (messages are in the box).
- On load: hydrate messages from the message box; if `threadJson` exists, use it
  to rebuild the active chain and backfill `messageIds` + message box.
- On save: extract messages from `threadJson` first (else from `messages`) and
  update `messageIds` + message box; cleanup orphaned message entries.

## 5. Compatibility & Migration
- New fields are nullable; legacy data loads unchanged.
- Backfill `parentId` on-the-fly when threads are loaded or appended.
- No migration script required for Phase 0/1/2.
- Phase 3 performs lazy backfill:
  - If legacy `Conversation.messages` is present, write into message box.
  - If `threadJson` exists, treat it as the source of truth for all message IDs.

## 6. Summary Policy (base chat)
- Base chat keeps `contextLength` truncation.
- Summary is backend-only, command-style: UI may trigger it later.
- Summarize **only** the active chain within current `contextLength` at trigger time.
- Summary range IDs are required to avoid stale/ambiguous summaries.

## 7. Risks
- Drift between `Conversation.messages` and `threadJson` if thread sync logic is not applied everywhere.
- Hive adapter updates must be kept in sync with model fields.
- UI assumes linear history; changes must not alter projection behavior.
- Message box cleanup must avoid deleting messages still referenced by threads.

## 8. Test / Verification (Phase 0/2)
- Send message, regenerate, and branch switching still behave correctly.
- Conversation reload uses existing `threadJson` and preserves UI history.
- parentId populated for newly created messages.
- No crash on old data with missing fields.
- Summary command writes `summary` + range IDs without UI changes.

---

## 9. Related Docs
- `specs/ui-rearchitecture/OWUI_MESSAGE_BRANCHING_SPEC.md`
- `docs/roleplay-feature/17-BRANCHING-ROLLBACK-AND-JOB-SAFETY.md`
- `docs/roleplay-feature/18-SNAPSHOT-ROLLBACK-TECHNICAL-DESIGN.md`
