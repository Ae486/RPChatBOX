# Think Bubble Redesign - Execution Plan

## Scope

Two features:
1. Header loading animation (waiting/streaming with no content)
2. Think bubble UX/UI overhaul (collapsible, timer, summary)

## Files to Modify

| File | Change |
|------|--------|
| `lib/chat_ui/owui/assistant_message.dart` | Replace old think bubble with new `OwuiThinkBubble` widget, add loading indicator |
| `lib/chat_ui/owui/chat_theme.dart` | Replace `thinkingDecoration()` with new inset grayscale style |
| `lib/chat_ui/owui/owui_icons.dart` | No change needed (already has `lightbulb`) |

## Preserved Behavior (DO NOT BREAK)

- `OwuiAssistantMessage` public API (constructor params) stays the same
- StreamManager data flow is untouched
- Body Markdown rendering is untouched
- Image grid rendering is untouched
- build.dart textMessageBuilder / customMessageBuilder call sites unchanged
- OwuiStableBody think block handling (backup path) not modified in this PR

---

## Step 1: Update `chat_theme.dart` - New Think Decoration

Replace `thinkingDecoration()`:

```dart
static BoxDecoration thinkingDecoration(BuildContext context) {
  final isDark = OwuiPalette.isDark(context);
  return BoxDecoration(
    color: isDark ? const Color(0xFF171717) : const Color(0xFFF9F9F9),
    borderRadius: BorderRadius.circular(12),
    border: Border.all(
      color: isDark
          ? Colors.white.withOpacity(0.1)
          : Colors.black.withOpacity(0.06),
    ),
  );
}
```

---

## Step 2: Create `OwuiThinkBubble` Widget in `assistant_message.dart`

New StatefulWidget replacing the old Container-based think section (lines 139-192).

### 2.1 Constructor

```dart
class OwuiThinkBubble extends StatefulWidget {
  final String thinkingContent;
  final bool isThinkingOpen;       // streaming: think tag still open
  final bool isCompleted;          // stream finished
  final DateTime? thinkingStartTime;
  final DateTime? thinkingEndTime;
  final double uiScale;

  const OwuiThinkBubble({...});
}
```

### 2.2 State Fields

```dart
class _OwuiThinkBubbleState extends State<OwuiThinkBubble>
    with SingleTickerProviderStateMixin {
  bool _expanded = false;
  Timer? _secondsTimer;
  int _displayedSeconds = 0;

  // Breathing animation
  late AnimationController _breatheController;
  late Animation<double> _breatheAnimation;

  // Expand/collapse animation
  // Use AnimatedCrossFade or AnimatedSize for height transition

  // Scroll auto-follow
  final ScrollController _scrollController = ScrollController();
  bool _userScrolledAway = false;
}
```

### 2.3 Timer Logic

- `initState`: if `isThinkingOpen && thinkingStartTime != null`, start `Timer.periodic(1s)` to increment `_displayedSeconds`
- `didUpdateWidget`: if `isCompleted` changes to true, cancel timer, freeze seconds
- `dispose`: cancel timer

Seconds calculation:
```dart
_displayedSeconds = widget.thinkingEndTime != null
    ? widget.thinkingEndTime!.difference(widget.thinkingStartTime!).inSeconds
    : DateTime.now().difference(widget.thinkingStartTime!).inSeconds;
```

### 2.4 Summary Extraction

Static utility:
```dart
static String? extractLatestBoldSummary(String content) {
  final matches = RegExp(r'\*\*([^*]+)\*\*').allMatches(content);
  if (matches.isEmpty) return null;
  final raw = matches.last.group(1)!.trim();
  return raw.length > 40 ? '${raw.substring(0, 40)}...' : raw;
}
```

Called on every build from `widget.thinkingContent`.

### 2.5 Breathing Animation

```dart
_breatheController = AnimationController(
  vsync: this,
  duration: const Duration(milliseconds: 1500),
)..repeat(reverse: true);

_breatheAnimation = Tween<double>(begin: 0.4, end: 1.0).animate(
  CurvedAnimation(parent: _breatheController, curve: Curves.easeInOut),
);
```

- When `isCompleted`: stop controller, set opacity to 1.0 (static)

### 2.6 Build - Collapsed Header Row

Layout structure:
```
GestureDetector(onTap: toggle expand)
  Container(decoration: thinkingDecoration)
    Row(
      children: [
        // 1. Lightbulb icon (breathing or static)
        AnimatedBuilder / Opacity(
          opacity: isThinking ? _breatheAnimation : 1.0,
          child: Icon(OwuiIcons.lightbulb, size: 14 * uiScale,
                      color: isThinking ? amber : gray500),
        ),

        SizedBox(width: 6 * uiScale),

        // 2. Timer (fixed min width to prevent overflow)
        // Use ConstrainedBox(constraints: BoxConstraints(minWidth: 0))
        // Timer text naturally takes its width, Expanded summary absorbs rest
        Text(
          isCompleted
              ? '已完成思考（用时${_displayedSeconds}秒）'
              : '${_displayedSeconds}秒',
          style: TextStyle(
            fontSize: 12 * uiScale,
            fontFeatures: [FontFeature.tabularFigures()],
            color: gray500,
          ),
        ),

        // 3. Divider + Summary (only when thinking, not completed)
        if (!isCompleted && summary != null) ...[
          Padding(
            padding: EdgeInsets.symmetric(horizontal: 8 * uiScale),
            child: Container(
              width: 1, height: 12 * uiScale,
              color: borderColor,
            ),
          ),
          Expanded(
            child: AnimatedSwitcher(
              duration: Duration(milliseconds: 200),
              child: Text(
                summary ?? '正在思考...',
                key: ValueKey(summary),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12 * uiScale,
                  fontStyle: FontStyle.italic,
                  color: gray500,
                ),
              ),
            ),
          ),
        ],

        // If completed, summary is gone, use Spacer
        if (isCompleted) const Spacer(),

        // No summary during thinking = show placeholder
        if (!isCompleted && summary == null)
          Expanded(
            child: Text('正在思考...', style: ...),
          ),

        // 4. Chevron (animated rotation)
        RotationTransition(
          turns: AlwaysStoppedAnimation(_expanded ? 0.5 : 0.0),
          // or animate via AnimatedRotation
          child: Icon(OwuiIcons.chevronDown, size: 14 * uiScale, color: gray500),
        ),
      ],
    )
```

**Overflow prevention strategy:**
- Timer text: intrinsic width only (no fixed constraint needed because numbers + "秒" is short)
- Summary: wrapped in `Expanded` → always fills remaining space, auto-ellipsis
- When completed: "已完成思考（用时999秒）" ← max ~14 chars + Spacer + chevron, no overflow risk
- All font sizes scale with `uiScale`

### 2.7 Build - Expanded Content Area

```dart
AnimatedSize(
  duration: Duration(milliseconds: 250),
  curve: Curves.fastOutSlowIn,
  clipBehavior: Clip.hardEdge,
  child: _expanded
      ? Column(
          children: [
            Divider(height: 1, color: borderColor),
            SizedBox(height: 4 * uiScale),
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: 160 * uiScale),
              child: ScrollConfiguration(
                behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
                child: ListView(
                  controller: _scrollController,
                  shrinkWrap: true,
                  physics: ClampingScrollPhysics(),
                  children: [
                    // Simple Markdown: bold, italic, inline code
                    _SimpleThinkingMarkdown(
                      text: widget.thinkingContent,
                      uiScale: widget.uiScale,
                      isDark: isDark,
                    ),
                  ],
                ),
              ),
            ),
          ],
        )
      : const SizedBox.shrink(),
)
```

### 2.8 Auto-follow Scroll

```dart
void _onThinkingContentChanged() {
  if (!_expanded || _userScrolledAway) return;
  WidgetsBinding.instance.addPostFrameCallback((_) {
    if (_scrollController.hasClients) {
      _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
    }
  });
}

// In initState:
_scrollController.addListener(() {
  final atBottom = _scrollController.position.pixels >=
      _scrollController.position.maxScrollExtent - 20;
  if (atBottom) {
    _userScrolledAway = false;
  } else if (_scrollController.position.userScrollDirection != ScrollDirection.idle) {
    _userScrolledAway = true;
  }
});
```

### 2.9 Simple Markdown Renderer

Lightweight widget for thinking content. Only renders:
- `**bold**` → Bold text
- `*italic*` → Italic text
- `` `code` `` → Inline code with background

Implementation: Use `Text.rich()` with a simple regex parser, or reuse `OwuiMarkdown` with minimal config. Since `OwuiMarkdown` already exists and handles all these, reuse it with `isStreaming: false` to avoid complex code block rendering overhead.

Decision: Reuse `OwuiMarkdown` (it already handles bold/italic/inline code). The "heavy" features (code blocks, tables) won't trigger if thinking content doesn't contain them.

---

## Step 3: Update `OwuiAssistantMessage.build()` in `assistant_message.dart`

### 3.1 Add Loading Indicator

After header row (line 137), before think bubble:

```dart
// Loading indicator: streaming with no content yet
if (isStreaming && bodyMarkdown.trim().isEmpty && thinking.trim().isEmpty && !thinkingOpen) {
  children.add(
    Padding(
      padding: EdgeInsets.only(bottom: 8 * uiScale),
      child: IsTypingIndicator(
        size: 5 * uiScale,
        color: OwuiPalette.textSecondary(context),
        spacing: 3 * uiScale,
      ),
    ),
  );
}
```

Import: `import 'package:flutter_chat_ui/flutter_chat_ui.dart';` for `IsTypingIndicator`.

### 3.2 Replace Think Bubble

Replace lines 139-193 (old Container-based think section) with:

```dart
if (thinking.trim().isNotEmpty || thinkingOpen) {
  children.add(
    Padding(
      padding: EdgeInsets.only(bottom: 10 * uiScale),
      child: OwuiThinkBubble(
        thinkingContent: thinking,
        isThinkingOpen: thinkingOpen,
        isCompleted: !thinkingOpen && thinking.trim().isNotEmpty,
        thinkingStartTime: streamData?.thinkingStartTime,
        thinkingEndTime: streamData?.thinkingEndTime,
        uiScale: uiScale,
      ),
    ),
  );
}
```

---

## Step 4: Remove Dead Code

- Delete `_ThinkingDots` class (lines 458-497) - no longer used
- Old thinking Container code is replaced in Step 3

---

## Step 5: Test Matrix

| Scenario | Expected Behavior |
|----------|-------------------|
| Stream starts, no content | Header → bouncing dots indicator |
| Think tag received, streaming | Collapsed bubble: breathing lightbulb + timer + summary |
| Expand during streaming | Content area shows, auto-follows |
| User scrolls up in expanded | Auto-follow pauses |
| User scrolls to bottom | Auto-follow resumes |
| Think tag closes | Lightbulb static, timer freezes, text → "已完成思考（用时xx秒）" |
| No bold in thinking content | Summary shows "正在思考..." |
| Bold summary changes rapidly | AnimatedSwitcher fades between values |
| History message with thinking | Collapsed, static, "已完成思考（用时xx秒）" |
| History message without thinking | No think bubble shown |
| uiScale = 1.5 | All sizes scale, no overflow |
| Timer 0→9→10→99→100 seconds | No layout jump, Expanded absorbs space |

---

## Color Reference

| Element | Dark Mode | Light Mode |
|---------|-----------|------------|
| Bubble background | `#171717` (gray900) | `#F9F9F9` (gray50) |
| Bubble border | `white @ 10%` | `black @ 6%` |
| Lightbulb (active) | `Colors.amber[400]` | `Colors.amber[600]` |
| Lightbulb (static) | `gray500` | `gray500` |
| Timer/Summary text | `gray500` | `gray500` |
| Divider line | Same as border | Same as border |
| Content text | `gray400` (dark) | `gray600` (light) |
| Border radius | 12px | 12px |

## Execution Order

1. Step 1 → chat_theme.dart
2. Step 2 → OwuiThinkBubble in assistant_message.dart
3. Step 3 → Update OwuiAssistantMessage.build()
4. Step 4 → Remove dead code
5. Step 5 → Manual test
