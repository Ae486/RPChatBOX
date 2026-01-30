# 键盘滚动优化修复文档

**日期**: 2026-01-30
**修复版本**: v2 (Delta-based approach)
**协作**: Claude Haiku 4.5 + Codex (OpenAI)

---

## 问题背景

### 官方 flutter_chat_ui 包的问题

1. **文本上移延迟**：100ms 防抖导致文本滚动严重滞后于键盘动画，产生可见的阶梯跳跃
2. **非底部也滚动**：用户在浏览历史消息时，键盘弹起仍会触发滚动，破坏浏览位置

### 本地 fork v1 的问题

尝试通过以下修改解决官方问题：
- 移除 100ms 防抖，改为逐帧调度（`scheduleFrameCallback`）
- 锁定 `baseOffset` 防止过度滚动
- 首帧判断是否在底部，非底部不滚动

但引入了新问题：
- **Issue 4**：短内容时键盘弹起产生"先上后下"抖动
- **Issue 5**：发送消息后键盘收起，滚动位置回退到发送前

---

## 根因分析

### Issue 4: 短内容抖动

**本地 fork v1 代码**:
```dart
// scheduleFrameCallback 在布局前执行
SchedulerBinding.instance.scheduleFrameCallback((_) {
  if (_keyboardOpenedNearBottom == null) {
    final extentAfter = _scrollController.position.extentAfter;
    _keyboardOpenedNearBottom = extentAfter <= 80.0;  // ← 测量时机错误
  }
});
```

**问题**：
- `scheduleFrameCallback` 在布局 pass **之前**执行
- 此时 viewport 还没缩小，`extentAfter` 测量的是旧状态
- 短内容时 `extentAfter` 本就很小，被误判为"在底部"
- 执行 `jumpTo(baseOffset + height)` 后，下一帧布局完成，Flutter 自动修正 → 抖动

**官方包为何没有**：
- 使用 `addPostFrameCallback`（布局后执行）
- 用 `min(..., maxScrollExtent)` clamp，短内容时 clamp 到 0，实际不滚动

### Issue 5: 发送消息后回退

**本地 fork v1 代码**:
```dart
_keyboardBaseOffset ??= _scrollController.offset;  // 键盘首帧锁定
...
final targetOffset = _keyboardBaseOffset! + effectiveHeight;
_scrollController.jumpTo(targetOffset);
```

**场景**：
1. 用户在底部（offset=500），键盘弹起
2. `_keyboardBaseOffset = 500`（锁定）
3. 键盘完全弹起，height=300，滚动到 800
4. 发送消息，`maxScrollExtent` 增加到 1000，应用层滚动到 1000
5. **但 `_keyboardBaseOffset` 仍然是 500**
6. 键盘收起过程中，height 从 300 逐帧减小
7. `targetOffset = 500 + 250 = 750`，`500 + 200 = 700`...
8. 最终 `targetOffset = 500 + 0 = 500` → **回退到发送前位置**

**官方包为何没有**：
```dart
_scrollController.jumpTo(
  min(_scrollController.offset + height, maxScrollExtent),
);
```
每帧用**当前 offset**，不锁定基准。

---

## 修复方案 (v2)

### 核心设计变更

| 旧方案（v1） | 新方案（v2） |
|-------------|-------------|
| `scheduleFrameCallback`（布局前） | `addPostFrameCallback`（布局后） |
| `baseOffset + height`（锁定基准） | `currentOffset + delta`（增量累加） |
| 只在首帧判断底部 | 允许用户滚动重新激活 |
| 无 clamp | 始终 clamp 到边界 |

### 算法伪代码

```dart
// 状态变量
bool _keyboardActive = false;
bool _keyboardAutoScroll = false;
double _lastKeyboardHeight = 0.0;

void onKeyboardHeightChanged(double height) {
  final nearBottom = extentAfter <= 80.0 || maxScrollExtent <= 0.0;
  final opening = _lastKeyboardHeight == 0.0 && height > 0.0;
  final closing = height == 0.0 && _lastKeyboardHeight > 0.0;

  if (opening) {
    _keyboardActive = true;
    _keyboardAutoScroll = nearBottom;  // 锁定决策
  }

  if (_keyboardAutoScroll && _keyboardActive) {
    final delta = height - _lastKeyboardHeight;  // 增量
    final target = (pixels + delta).clamp(min, max);  // 应用到当前 offset + clamp
    if (abs(target - pixels) > 0.5) {
      jumpTo(target);
    }
  }

  _lastKeyboardHeight = height;

  if (closing) {
    _keyboardActive = false;
    _keyboardAutoScroll = false;
    _lastKeyboardHeight = 0.0;
  }
}
```

### 用户滚动感知（可选增强）

```dart
void _handleUserScrollDuringKeyboard() {
  if (!_keyboardActive) return;
  final nearBottom = extentAfter <= 80.0 || maxScrollExtent <= 0.0;

  if (!nearBottom && _keyboardAutoScroll) {
    _keyboardAutoScroll = false;  // 用户滚离底部，停止自动跟随
  } else if (nearBottom && !_keyboardAutoScroll) {
    _keyboardAutoScroll = true;  // 用户滚回底部，恢复自动跟随
    _lastKeyboardHeight = currentKeyboardHeight;  // 重置基线防止跳跃
  }
}
```

---

## 实施细节

### 修改 1: keyboard_mixin.dart

**位置**: `packages/flutter_chat_ui/lib/src/utils/keyboard_mixin.dart`

**变更**:
```diff
- import 'package:flutter/scheduler.dart';
  import 'package:flutter/material.dart';

  void didChangeMetrics() {
    if (!mounted || _frameScheduled) return;
    _frameScheduled = true;
-   SchedulerBinding.instance.scheduleFrameCallback((_) {
+   WidgetsBinding.instance.addPostFrameCallback((_) {
      _frameScheduled = false;
      if (!mounted) return;

      final adjustedHeight = max(keyboardHeight / pixelRatio - _initialSafeArea, 0.0);
      if ((adjustedHeight - _previousKeyboardHeight).abs() < 0.5) return;
      _previousKeyboardHeight = adjustedHeight;

      onKeyboardHeightChanged(adjustedHeight);
    });
  }
```

### 修改 2: chat_animated_list.dart - 状态变量

**位置**: `packages/flutter_chat_ui/lib/src/chat_animated_list/chat_animated_list.dart` (第 222-231 行)

**变更**:
```diff
- double? _keyboardBaseOffset;
- double? _keyboardBaseViewportSlack;
- bool? _keyboardOpenedNearBottom;
+ bool _keyboardActive = false;
+ bool _keyboardAutoScroll = false;
+ double _lastKeyboardHeight = 0.0;
```

### 修改 3: chat_animated_list.dart - onKeyboardHeightChanged

**位置**: 第 290-348 行

**完整替换为**:
```dart
void onKeyboardHeightChanged(double height) {
  if (widget.reversed) return;
  if (!mounted || !_scrollController.hasClients) return;

  const nearBottomThreshold = 80.0;
  final metrics = _scrollController.position;
  final nearBottom = metrics.extentAfter <= nearBottomThreshold ||
      metrics.maxScrollExtent <= 0.0;

  final opening = _lastKeyboardHeight == 0.0 && height > 0.0;
  final closing = height == 0.0 && _lastKeyboardHeight > 0.0;

  if (opening) {
    _keyboardActive = true;
    _keyboardAutoScroll = nearBottom;
  }

  if (_keyboardAutoScroll && _keyboardActive) {
    final delta = height - _lastKeyboardHeight;
    final target = (metrics.pixels + delta)
        .clamp(metrics.minScrollExtent, metrics.maxScrollExtent);
    if ((target - metrics.pixels).abs() > 0.5) {
      _scrollController.jumpTo(target);
    }
  }

  _lastKeyboardHeight = height;

  if (closing) {
    _keyboardActive = false;
    _keyboardAutoScroll = false;
    _lastKeyboardHeight = 0.0;
  }

  if (_keyboardActive) {
    _scrollToBottomShowTimer?.cancel();
  }
}
```

### 修改 4: chat_animated_list.dart - 用户滚动感知

**位置**: 在 `onKeyboardHeightChanged` 后添加新方法

```dart
void _handleUserScrollDuringKeyboard() {
  if (!_keyboardActive || !_scrollController.hasClients) return;

  const nearBottomThreshold = 80.0;
  final metrics = _scrollController.position;
  final nearBottom = metrics.extentAfter <= nearBottomThreshold ||
      metrics.maxScrollExtent <= 0.0;

  if (!nearBottom && _keyboardAutoScroll) {
    _keyboardAutoScroll = false;
  } else if (nearBottom && !_keyboardAutoScroll) {
    _keyboardAutoScroll = true;
    final view = View.of(context);
    final pixelRatio = MediaQuery.of(context).devicePixelRatio;
    final initialSafeArea = MediaQuery.of(context).padding.bottom;
    _lastKeyboardHeight =
        max(view.viewInsets.bottom / pixelRatio - initialSafeArea, 0.0);
  }
}
```

**集成点**: 在 `UserScrollNotification` 处理中调用（第 460 行附近）

```diff
  if (notification is UserScrollNotification) {
+   _handleUserScrollDuringKeyboard();
    // 原有逻辑...
  }
```

---

## 验证矩阵

| 场景 | 预期行为 | 状态 |
|-----|---------|-----|
| 正常底部键盘弹起 | 文本平滑跟随上移 | ✓ 待测试 |
| 非底部键盘弹起 | 文本不滚动 | ✓ 待测试 |
| 短内容键盘弹起 | 无抖动 | ✓ 待测试 |
| 发送消息后键盘收起 | 停在新消息位置 | ✓ 待测试 |
| 键盘开启中滚动离开 | 停止自动跟随 | ✓ 待测试 |
| 键盘开启中滚回底部 | 恢复自动跟随 | ✓ 待测试 |

---

## 技术要点

### 为什么 delta 模式能解决 Issue 5？

**关键**：每帧都用**当前 offset**，不锁定基准。

```dart
// v1 (baseOffset 锁定)
targetOffset = baseOffset + height;  // baseOffset 在首帧锁定，发送消息后不更新

// v2 (delta 增量)
delta = height - lastHeight;
targetOffset = currentOffset + delta;  // currentOffset 是实时的，包含发送消息后的滚动
```

当发送消息后 `maxScrollExtent` 增加，应用层调用 `scrollToIndex` 滚动到新位置，`currentOffset` 已经更新。下一帧键盘回调时，delta 应用到新的 `currentOffset`，不会回退。

### 为什么 addPostFrameCallback 能解决 Issue 4？

**关键**：布局后测量，`extentAfter` 反映的是缩小后的 viewport 状态。

```
帧 N:
  ├── didChangeMetrics() → scheduleFrameCallback (v1) 或 addPostFrameCallback (v2)
  ├── 布局 pass → viewport 缩小
  ├── 绘制 pass
  └── 帧结束

帧 N+1:
  ├── scheduleFrameCallback 执行 (v1) ← extentAfter 是旧值
  ├── 布局 pass
  ├── 绘制 pass
  └── addPostFrameCallback 执行 (v2) ← extentAfter 是新值
```

v2 在布局完成后测量，短内容时 `maxScrollExtent <= 0` 判断准确，加上 clamp 保护，不会产生抖动。

### 为什么需要 clamp？

```dart
final target = (pixels + delta).clamp(minScrollExtent, maxScrollExtent);
```

**场景 1**：短内容，`maxScrollExtent = 0`，键盘弹起 `delta > 0`，`target = 0 + delta` 会超出边界，clamp 到 0。

**场景 2**：键盘收起，`delta < 0`，`target = pixels + delta` 可能小于 0，clamp 到 `minScrollExtent`。

clamp 确保滚动位置始终在合法范围内，防止 Flutter 抛出异常或产生意外行为。

---

## 协作记录

### Codex 贡献

- 提出 delta-based 增量模式替代 baseOffset 锁定
- 设计用户滚动感知的 opt-in/opt-out 机制
- 明确 `addPostFrameCallback` vs `scheduleFrameCallback` 的时序差异
- 强调 clamp 的必要性

### Claude 实施

- 完整代码实现和集成
- 根因分析和文档编写
- 编译验证和测试准备

---

## 后续工作

1. **功能测试**：按验证矩阵逐项测试
2. **性能测试**：确认逐帧调度不会导致性能问题
3. **边界测试**：极短内容（1-2 条消息）、极长内容（1000+ 条消息）
4. **回归测试**：确保不影响 reversed 模式、流式输出等现有功能

---

## Codex 代码审查反馈 (v2.1 修复)

### 问题 1: Safe-area 基线过时 (High)

**问题**: `_initialSafeArea` 在 `didChangeDependencies` 中只捕获一次，旋转/分屏时会过时。

**修复**: 改用 `MediaQuery.viewInsets.bottom - MediaQuery.viewPadding.bottom` 实时计算。

```dart
double _effectiveKeyboardHeight() {
  final mediaQuery = MediaQuery.of(context);
  return max(mediaQuery.viewInsets.bottom - mediaQuery.viewPadding.bottom, 0.0);
}
```

### 问题 2: jumpTo 可能抛异常 (Medium)

**问题**: `hasClients` 检查和 `jumpTo` 之间可能发生 detach。

**修复**: 在 `jumpTo` 前再次检查 `hasClients`。

### 问题 3: 与用户拖拽冲突 (Medium)

**问题**: 键盘回调可能在用户拖拽时触发，导致滚动冲突。

**修复**: 检测 `isScrollingNotifier.value && userScrollDirection != idle` 时跳过。

```dart
if (position.isScrollingNotifier.value &&
    position.userScrollDirection != ScrollDirection.idle) {
  return;
}
```

### 问题 4: 阈值不一致 (Low)

**问题**: 0.5px 和 0.0 阈值在多处使用，浮动键盘可能导致状态卡住。

**修复**: 统一使用 `heightEpsilon = 1.0` 常量。

### 问题 5: 代码重复 (Low)

**问题**: `_handleUserScrollDuringKeyboard` 中的键盘高度计算与 mixin 不一致。

**修复**: 使用相同的 `viewInsets.bottom - viewPadding.bottom` 公式。

---

## 参考

- 原始研究文档: `docs/keyboard-scroll-research.md`
- Flutter Issue: https://github.com/flutter/flutter/issues/89914
- 官方 flutter_chat_ui: https://github.com/flyerhq/flutter_chat_ui
- Codex Session ID: `019c0b33-8c82-7b30-a5b8-fb834d647254`
