# 键盘/输入框/文本滚动 全链路研究报告

## 一、本地化 flutter_chat_ui 框架修改清单

### 修改 1: keyboard_mixin.dart（第 9-11 行）

**修改内容**：移除 100ms 防抖，改为每帧调度（`scheduleFrameCallback`）

**原始框架行为**：
- 使用 `Timer(Duration(milliseconds: 100), ...)` 防抖
- 每 100ms 最多触发一次 `onKeyboardHeightChanged`
- 键盘动画约 250ms，防抖期间只能触发 2-3 次回调

**修改后行为**：
- 使用 `SchedulerBinding.instance.scheduleFrameCallback` 代替 Timer
- 用 `_frameScheduled` 标志防止同帧重复调度
- 每帧（~16ms）触发一次，键盘动画期间约 15 次回调

**解决的问题**：内容滚动严重滞后于键盘动画（100ms 间隔导致可见的阶梯跳跃）

### 修改 2: chat_animated_list.dart（第 222-230 行）

**新增三个状态变量**：

```dart
double? _keyboardBaseOffset;          // 键盘开始弹起时的滚动偏移量
double? _keyboardBaseViewportSlack;   // 内容短于视口时的空余空间
bool? _keyboardOpenedNearBottom;      // 键盘首帧时是否在底部附近
```

**解决的问题**：去掉防抖后，每帧都触发 `jumpTo`，如果每次都用当前 offset 累加，会导致过度滚动。用 baseOffset 锁定基准点，从同一起点计算目标位置。

### 修改 3: chat_animated_list.dart（第 309-348 行）

**重写 `onKeyboardHeightChanged` 逻辑**：

```dart
// 1. 首帧锁定"是否在底部"（用 extentAfter 而非 maxScrollExtent）
// 2. 不在底部 → return（不干预）
// 3. 在底部 → 锁定 baseOffset + 计算 slack → jumpTo(baseOffset + effectiveHeight)
```

**解决的问题**：
- 非底部时不产生任何滚动（用户正在浏览历史）
- 底部时精确补偿键盘高度（内容跟随输入框上移）

---

## 二、输入框上移和文本上移的代码位置与逻辑

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│  Scaffold (resizeToAvoidBottomInset: true，默认值)            │
│  ├── AppBar                                                  │
│  └── body: ConversationViewV2 → Chat widget                  │
│       └── Stack                                              │
│           ├── CustomScrollView (填满 Stack)                   │
│           │   ├── SliverPadding (topPadding)                 │
│           │   ├── SliverAnimatedList (消息列表)                │
│           │   └── SliverSpacing (padding = composerHeight)   │
│           │       └── KeyboardMixin (检测键盘高度变化)         │
│           └── OwuiComposer (Positioned bottom:0)             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 输入框上移的实现（谁负责？）

**负责者**：Flutter 框架的 `Scaffold` + CSS-like 布局

**机制**：
1. `Scaffold.resizeToAvoidBottomInset` 默认为 `true`
2. 键盘弹起时，Scaffold 的 body 区域自动缩小（减去键盘高度）
3. `Chat` widget 在 body 内，其 `Stack` 也随之缩小
4. `OwuiComposer` 使用 `Positioned(left:0, right:0, bottom:0)` 定位
5. Stack 缩小 → `bottom:0` 的实际像素位置上移 → 输入框上移

**关键代码**：
- `chat.dart:163`: `Stack` 包含 ChatAnimatedList 和 Composer
- `owui_composer.dart:401`: `Positioned(left:0, right:0, bottom:0)`
- **没有手动代码控制输入框的上移**，完全由 Scaffold 的布局机制自动处理

**时序**：布局pass内完成，与键盘动画**同帧同步**

### 2.3 文本内容上移的实现（谁负责？）

**负责者**：`ChatAnimatedList.onKeyboardHeightChanged` + `KeyboardMixin`

**机制**：
1. `SliverSpacing` 混入 `KeyboardMixin`，监听 `WidgetsBinding.didChangeMetrics`
2. 键盘高度变化 → `didChangeMetrics()` → `scheduleFrameCallback`
3. 下一帧开始时回调执行 → 计算 adjustedHeight → 调用 `onKeyboardHeightChanged(height)`
4. `ChatAnimatedList.onKeyboardHeightChanged` 检查是否在底部附近
5. 如果在底部 → `_scrollController.jumpTo(baseOffset + effectiveHeight)`

**关键代码路径**：
```
keyboard_mixin.dart:46  didChangeMetrics()
  → keyboard_mixin.dart:51  scheduleFrameCallback
    → keyboard_mixin.dart:64  onKeyboardHeightChanged(adjustedHeight)
      → sliver_spacing.dart:60  转发给 widget.onKeyboardHeightChanged
        → chat_animated_list.dart:290  onKeyboardHeightChanged(height)
          → chat_animated_list.dart:344  _scrollController.jumpTo(targetOffset)
```

**时序**：比键盘动画帧**晚 1 帧**（scheduleFrameCallback 在下一帧开头执行）

### 2.4 时序对比

```
帧 N:
  ├── 键盘高度变化 → viewInsets 更新
  ├── Scaffold 重新布局 → body 缩小
  ├── Stack 缩小 → Composer(bottom:0) 上移     ← 输入框在此帧移动
  ├── CustomScrollView viewport 缩小
  ├── 当前 scrollOffset 不变，底部内容被键盘遮挡
  └── didChangeMetrics() → _frameScheduled = true

帧 N+1:
  ├── scheduleFrameCallback 执行
  ├── 计算 adjustedHeight
  ├── onKeyboardHeightChanged(height)
  └── jumpTo(baseOffset + height)              ← 内容在此帧移动

结论：输入框和内容存在 1 帧（~16ms）的天然延迟
```

---

## 三、"非底部不滚动、底部同步滚动"的实现

### 3.1 判断逻辑（chat_animated_list.dart:309-321）

```dart
void onKeyboardHeightChanged(double height) {
  if (widget.reversed) return;          // reversed 不处理

  if (height <= 0.5) {                  // 键盘关闭 → 清理状态
    _keyboardBaseOffset = null;
    _keyboardBaseViewportSlack = null;
    _keyboardOpenedNearBottom = null;
    return;
  }

  // 首帧锁定决策
  if (_keyboardOpenedNearBottom == null) {
    const nearBottomThreshold = 80.0;
    final extentAfter = _scrollController.position.extentAfter;
    _keyboardOpenedNearBottom = extentAfter <= nearBottomThreshold;
  }

  // 非底部 → 完全不干预滚动
  if (!_keyboardOpenedNearBottom!) return;

  // 底部 → 补偿滚动
  _keyboardBaseOffset ??= _scrollController.offset;
  _keyboardBaseViewportSlack ??= max(0.0,
    _scrollController.position.viewportDimension -
    _scrollController.position.extentInside);
  final effectiveHeight = max(0.0, height - _keyboardBaseViewportSlack!);
  final targetOffset = _keyboardBaseOffset! + effectiveHeight;
  _scrollController.jumpTo(targetOffset);
}
```

### 3.2 状态流转

```
键盘弹起首帧:
  extentAfter ≤ 80 → _keyboardOpenedNearBottom = true (在底部)
  extentAfter > 80 → _keyboardOpenedNearBottom = false (不在底部)

                 ┌─ true → 锁定 baseOffset → 每帧 jumpTo(baseOffset + height)
_nearBottom ─────┤
                 └─ false → return (不做任何事)

键盘关闭 (height ≤ 0.5):
  清空所有三个状态变量 → 等待下次键盘弹起重新判断
```

### 3.3 辅助机制：SliverSpacing 的 composerHeight 填充

```dart
// sliver_spacing.dart:47-54
SliverPadding(
  padding: EdgeInsets.only(
    bottom: heightNotifier.height +          // composerHeight
            (widget.bottomPadding ?? 0) +    // 可选 padding
            (widget.handleSafeArea == true ? safeArea : 0),
  ),
)
```

**作用**：在消息列表末尾留出 Composer 高度的空白，确保最后一条消息不被 Composer 遮挡。
**注意**：此 padding **不包含键盘高度**，键盘空间由 Scaffold 的 resize 处理。

### 3.4 真正起作用的代码（排除冗余）

| 功能 | 真正负责的代码 | 路径 |
|------|--------------|------|
| 输入框上移 | Scaffold.resizeToAvoidBottomInset + Positioned(bottom:0) | Flutter 框架原生 |
| 内容滚动补偿 | ChatAnimatedList.onKeyboardHeightChanged + jumpTo | chat_animated_list.dart:290-348 |
| 键盘高度检测 | KeyboardMixin.didChangeMetrics + scheduleFrameCallback | keyboard_mixin.dart:46-66 |
| 高度事件传递 | SliverSpacing 混入 KeyboardMixin → callback → ChatAnimatedList | sliver_spacing.dart:60-61 |
| 消息列表底部填充 | SliverSpacing (composerHeight padding) | sliver_spacing.dart:47-54 |
| Composer 高度通知 | OwuiComposer._measure → ComposerHeightNotifier | owui_composer.dart:128-146 |

**应用层** (`scroll_and_highlight.dart`) 的 `_requestAutoFollow` 和 `_handleChatScrollNotification` **不参与键盘弹起时的滚动处理**，它们负责的是发送消息后/流式输出时的自动跟随。

---

## 四、已知问题与修复规划

### 问题 4：短内容时键盘弹起产生"先上后下"抖动

**根因**：`scheduleFrameCallback` 在布局前执行，此时 `extentAfter` 测量不准确。
短内容时 `maxScrollExtent ≈ 0`，`extentAfter` 也很小，被误判为"在底部"。

**修复方案**：
1. 将回调从 `scheduleFrameCallback` 改为 `addPostFrameCallback`（布局后执行）
2. 添加 `maxScrollExtent <= 0` 守卫（内容不超出视口时不滚动）
3. `effectiveHeight <= 0` 时直接 return（slack 足够吸收键盘高度）

### 问题 5：发送消息后键盘收起，位置回退到发送前

**根因**：
- 键盘关闭时 `height ≤ 0.5` 分支只清理状态，不处理滚动
- 键盘关闭过程中（高度逐帧减小），公式 `baseOffset + effectiveHeight` 中的
  `baseOffset` 是发送消息前捕获的旧值，导致滚动位置逐帧回退到旧位置

**修复方案**：
1. 新增 `_lastKeyboardHeight` 追踪方向（打开 vs 关闭）
2. 新增 `_keyboardPinned` 标志记住"用户在底部"状态
3. 键盘关闭阶段（`height < _lastKeyboardHeight`）：跳过 jumpTo 逻辑
4. 键盘完全关闭（`height ≤ 0.5`）：如果 `_keyboardPinned && !_userHasScrolled`，执行 `jumpTo(maxScrollExtent)` 滚到新的底部

### 修改范围

**仅修改一个文件**：`packages/flutter_chat_ui/lib/src/chat_animated_list/chat_animated_list.dart`

可选优化：`keyboard_mixin.dart` 将 `scheduleFrameCallback` 改为 `addPostFrameCallback`（从源头解决测量时序问题）

**不需要修改**：
- `sliver_spacing.dart`（纯转发，逻辑无误）
- `owui_composer.dart`（输入框定位由 Scaffold 处理）
- `scroll_and_highlight.dart`（应用层，不参与键盘滚动）
- `conversation_view_v2.dart` 及其 part 文件
