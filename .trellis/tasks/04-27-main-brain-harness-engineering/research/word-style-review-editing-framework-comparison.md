# Word-Style Review Editing Framework Comparison

Date: 2026-05-03

## 1. Conclusion

The target capability should be modeled as **review events** rather than as plain object diffs.

For the project, the useful split is:

1. Capture user intent at the editor layer when possible:
   - tracked revision: insert / delete / replace / format
   - comment thread: anchored note / suggestion / question / resolved state
2. Normalize those editor events into a project-owned event contract.
3. Feed the normalized events into setup and longform agent context.
4. Keep `DeepDiff` / `difflib` as a fallback and audit tool, not as the primary Word-style review model.

SuperDoc is currently the closest off-the-shelf match. It already has tracked changes, comments, DOCX-oriented review semantics, ProseMirror/Yjs internals, and integration callbacks. The main risks are license and Flutter integration shape.

## 2. Current Project Anchors

- Setup already has the storage and context plumbing:
  - `SetupPendingUserEditDeltaRecord.changes_json`
  - `PendingUserEditDelta.changes`
  - `SetupContextBuilder` injects pending user edit deltas into `context_packet.user_edit_deltas`
  - `SetupAgentRuntimeStateService.reconcile_snapshot()` invalidates cognition when pending user edit delta ids exist
  - setup tools carry `user_edit_delta_ids` when a later tool action reconciles a user edit
- Current model is still old diff-shaped:
  - `path`
  - `change_kind = add | remove | replace`
  - `before_value`
  - `after_value`
  - `text_diff`
- Existing app already depends on `webview_flutter` and `webview_windows`, so a WebView-backed editor bridge is technically plausible.
- The capability is not setup-only. Longform runtime needs the same review event model for pending story segments, accepted/proposed text, and author comments.

## 3. Candidate Comparison

| Candidate | Layer | What it gives | Fit for this project | Main risk |
|---|---|---|---|---|
| SuperDoc | Full Web/DOCX review editor | Track changes, comments, accept/reject hooks, DOCX-oriented review model, ProseMirror/Yjs internals | Best off-the-shelf match for Word-style revisions/comments | AGPL/commercial licensing; JS/Vue/WebView integration; normalize DOCX/editor payloads into our JSON draft model |
| CKEditor 5 Track Changes + Comments | Full Web editor, mature commercial collaboration stack | Suggestions, comment threads, adapter persistence, accept/reject workflow | Strong enterprise reference, viable if commercial web editor is acceptable | Premium/commercial feature surface; heavier integration; less aligned with Flutter-native UI |
| Tiptap Pro Tracked Changes + Comments | ProseMirror-based Web editor extension stack | Comments and tracked changes as Pro extensions on top of ProseMirror/Yjs | Good design reference for ProseMirror/Yjs-native apps | Paid/beta extension surface; not Flutter-native; implementation details less accessible |
| ProseMirror + Yjs | Low-level Web editing/collaboration primitives | Transactions, steps, decorations, plugin state, stable collaborative positions | Best if building a custom Web editor from primitives | High implementation cost; no built-in review workflow |
| AppFlowy Editor | Flutter-native editor framework | Document tree, transaction/operation system, Quill-like Delta for text changes, import/export plugins | Best Flutter-native base if we build review events ourselves | No native track changes/comments found in current docs/source summary; review layer must be custom |
| SuperEditor | Flutter-native editor framework | Document nodes, editor requests/commands/events, attributions/annotations | Good low-level Flutter-native editing base | No native Word-style review workflow; custom persistence and comment UI needed |
| Quill Delta / Flutter Quill | Text operation data model and editor family | Insert/delete/retain ops with attributes | Useful as a text operation representation, especially for longform text | Not enough by itself for comments, suggestion lifecycle, accept/reject, or stable cross-edit anchoring |
| DeepDiff + difflib | Backend diff fallback | Deterministic object diff and local text diff | Useful fallback when editor-native operation stream is unavailable | Loses user intent; weak for comments/suggestions; hard to anchor after later edits |

## 4. SuperDoc Deep Notes

Source basis:

- SuperDoc official docs and repository material.
- DeepWiki repository analysis for `superdoc-dev/superdoc`.

Relevant design facts:

- Internals:
  - Vue 3 app shell.
  - Pinia stores for editor/comment state.
  - Hidden ProseMirror editor state.
  - Custom document rendering / pagination pipeline.
  - Yjs collaboration support.
- Review features:
  - document mode can enable tracked changes / suggesting behavior.
  - comments and tracked changes are first-class review objects.
  - tracked-change comments can be rebuilt from editor state.
  - accept/reject behavior can be customized through callbacks.
  - permission resolver can control who resolves comments or accepts changes.
- Integration callbacks worth inspecting in source:
  - `onCommentsUpdate`
  - `onCommentsListChange`
  - `onTransaction`
  - `trackedChangesUpdate`
  - `onTrackedChangeBubbleAccept`
  - `onTrackedChangeBubbleReject`
  - comment click / position update callbacks
- License:
  - open-source AGPLv3 plus commercial/enterprise option.

Project reading:

- If license and WebView/web module integration are acceptable, SuperDoc can be the fastest path to real Word-like behavior.
- The project should not persist raw SuperDoc payloads as agent context. It should normalize them into project review events.
- SuperDoc source should be pulled before implementation to inspect exact payload shape, especially comment/update events and DOCX revision identifiers.

## 5. CKEditor 5 Deep Notes

Source basis:

- CKEditor official track changes and comments documentation.

Relevant design facts:

- Track changes is modeled as suggestions.
- Comments are threads anchored to document ranges.
- Persistence is usually handled through adapters:
  - load existing suggestions/comments
  - create/update/delete suggestion state
  - accept/reject or resolve through editor APIs
- Mature collaboration UX:
  - sidebar / inline balloons
  - author metadata
  - accept/reject workflow
  - comment resolution workflow

Project reading:

- CKEditor is a strong product reference for the lifecycle:
  - suggestion opened -> modified -> accepted/rejected
  - comment opened -> replied/resolved
  - adapter persists review data separately from document content
- It is less attractive as the primary integration unless the project accepts a commercial Web editor stack.

## 6. Tiptap / ProseMirror / Yjs Deep Notes

Source basis:

- Tiptap official comments / tracked-changes docs.
- ProseMirror official guide.
- Yjs official docs and repository analysis.

Relevant design facts:

- Tiptap comments and tracked changes are Pro extensions.
- Tiptap is built on ProseMirror transactions and plugins.
- Collaboration uses Yjs.
- ProseMirror provides:
  - transactions
  - steps
  - plugin state
  - decorations for visual annotations
  - document position mapping
- Yjs provides:
  - CRDT document updates
  - relative positions that survive concurrent edits better than raw offsets

Project reading:

- Best design lesson: a review event needs both a semantic payload and a durable anchor.
- Raw character offsets are fragile after edits. Prefer:
  - target block / node id
  - base revision
  - quote anchor
  - context before / after
  - optional editor-native relative position
- Tiptap/ProseMirror/Yjs are better as implementation references than as the preferred direct dependency unless the project chooses a Web editor route.

## 7. Flutter-Native Options

### AppFlowy Editor

Source basis:

- AppFlowy Editor repository/package docs and DeepWiki repository analysis.

Relevant design facts:

- Flutter-native.
- Document is a tree of nodes.
- Changes are applied through transactions.
- Transactions contain operations:
  - insert node
  - delete node
  - update node attributes
  - update text through Delta
- Text uses a Quill-like Delta model.
- Import/export plugin system exists.

Project reading:

- Best Flutter-native base if the project wants full UI ownership.
- It gives a usable operation stream, but not a ready Word-style review workflow.
- Track changes/comments would need to be built as an application layer:
  - capture transactions
  - convert operations into review events
  - render revision/comment decorations
  - implement accept/reject/resolve actions

### SuperEditor

Source basis:

- SuperEditor repository/wiki and DeepWiki repository analysis.

Relevant design facts:

- Flutter-native.
- Document-based editor.
- Editing pipeline:
  - edit request
  - edit command
  - document/composer mutation
  - edit events / reactions
- Rich text uses attributions/metadata spans.

Project reading:

- Good if we need a lower-level Flutter editor and are comfortable building much of the review layer.
- Similar to AppFlowy, it is a base editor, not a Word-style review product.

## 8. Recommended Project Architecture

Do not make setup-specific `user_edit_delta` the primary concept.

Introduce a shared review-event concept, then adapt it into setup and longform surfaces.

Suggested normalized event shape:

```json
{
  "schema_version": "review_event.v1",
  "event_id": "review_evt_001",
  "event_type": "revision",
  "revision_kind": "replace",
  "status": "open",
  "source": "user",
  "target": {
    "scope": "setup",
    "target_ref": "foundation:magic-law",
    "target_block": "foundation_entry",
    "path": "content",
    "base_revision": 3
  },
  "anchor": {
    "quote": "old local text",
    "range": {"start": 120, "end": 148},
    "context_before": "text before",
    "context_after": "text after",
    "native_anchor": {
      "kind": "superdoc",
      "id": "optional editor native id"
    }
  },
  "change": {
    "before_text": "old local text",
    "after_text": "new local text",
    "before_value": null,
    "after_value": null
  },
  "comment": null,
  "created_at": "2026-05-03T00:00:00Z"
}
```

For comments:

```json
{
  "schema_version": "review_event.v1",
  "event_id": "review_evt_002",
  "event_type": "comment",
  "status": "open",
  "target": {
    "scope": "longform",
    "target_ref": "segment:pending:seg_001",
    "target_block": "story_segment",
    "path": "body",
    "base_revision": 7
  },
  "anchor": {
    "quote": "the sentence under review",
    "context_before": "previous sentence",
    "context_after": "next sentence"
  },
  "comment": {
    "thread_id": "thread_001",
    "comment_id": "comment_001",
    "text": "This should be colder and less explanatory.",
    "resolved_at": null
  }
}
```

### Setup adaptation

- Keep `rp_setup_pending_user_edit_deltas` for now.
- Store normalized review events inside `changes_json`.
- Add `schema_version` to each item.
- Keep old `UserEditChangeItem` readable for backward compatibility until migration.
- `SetupContextBuilder` can continue injecting `user_edit_deltas`, but the prompt renderer should display them as:
  - user revised target X from A to B
  - user deleted target X
  - user commented on target X: ...
  - user suggestion remains unresolved

### Longform adaptation

- Reuse the same review-event model.
- Target refs should point to:
  - pending segment ids
  - accepted segment ids
  - chapter draft blocks
  - author notes / metadata sidecars if needed
- Longform writer/orchestrator should receive bounded open review events, not the whole editor event history.

## 9. What To Pull Locally If We Need Source

Pull source only after the route is chosen. For the next source-read pass, priority should be:

1. `superdoc-dev/superdoc`
   - inspect exact event payloads for comments/tracked changes
   - inspect accept/reject hooks
   - inspect export/import behavior
   - inspect license/build/integration constraints
2. `AppFlowy-IO/appflowy-editor`
   - inspect transaction/operation payloads
   - inspect how to attach custom metadata/decorations
   - estimate Flutter-native track-change implementation cost
3. `superlistapp/super_editor`
   - inspect edit event pipeline and attribution extension points
   - compare against AppFlowy for custom review overlay cost

Do not pull CKEditor/Tiptap source unless the project seriously considers a commercial Web editor route. Their official docs are enough for architecture reference.

## 10. Recommendation

Use SuperDoc as the primary reference and likely prototype target.

Recommended decision path:

1. Prototype feasibility:
   - embed SuperDoc in WebView or a local web route
   - capture `onCommentsUpdate` / tracked-change callbacks
   - normalize one revision and one comment into `review_event.v1`
2. In parallel, keep a Flutter-native fallback:
   - AppFlowy Editor is the stronger native candidate because its transaction + Delta model already resembles edit-event capture
3. Preserve backend compatibility:
   - keep current `PendingUserEditDelta` concept
   - evolve `changes_json` into `review_event.v1[]`
   - keep DeepDiff/difflib as fallback for plain JSON draft edits and audit

This keeps the feature from becoming setup-only and lets longform runtime consume the same review-event shape.

## 11. User Decision Note

Confirmed on 2026-05-03:

- This is not the current implementation focus.
- If the capability can be prototyped quickly, introducing a WebView-backed editor is acceptable.
- The preferred direction is to reference SuperDoc for Word-style tracked changes and comments.
- WebView should be treated as a specialized editor component, not as a full-page replacement for Flutter UI.
- Flutter remains the main application shell for setup/runtime/session/tooling surfaces.
- The future integration should pass normalized review events between the editor and backend rather than syncing full document state on every keystroke.

## 12. Source Links

- SuperDoc docs: https://docs.superdoc.dev/
- SuperDoc GitHub: https://github.com/superdoc-dev/superdoc
- CKEditor Track Changes docs: https://ckeditor.com/docs/ckeditor5/latest/features/collaboration/track-changes/track-changes.html
- CKEditor Comments docs: https://ckeditor.com/docs/ckeditor5/latest/features/collaboration/comments/comments.html
- Tiptap Tracked Changes docs: https://tiptap.dev/docs/tracked-changes/getting-started/overview
- Tiptap Comments docs: https://tiptap.dev/docs/comments/getting-started/overview
- ProseMirror guide: https://prosemirror.net/docs/guide/
- Yjs docs: https://docs.yjs.dev/
- AppFlowy Editor GitHub: https://github.com/AppFlowy-IO/appflowy-editor
- AppFlowy Editor package: https://pub.dev/packages/appflowy_editor
- SuperEditor GitHub: https://github.com/superlistapp/super_editor
- SuperEditor package: https://pub.dev/packages/super_editor
- Quill Delta docs: https://quilljs.com/docs/delta
