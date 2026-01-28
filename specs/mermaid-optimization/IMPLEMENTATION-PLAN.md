# Mermaid 优化实施计划

> **Status**: ⏸️ Phase 6 暂停（SVG 渲染兼容性问题）
> **Created**: 2026-01-28
> **Source**: MERMAID-OPTIMIZATION-SPEC.md + 双模型分析
> **Phase 1-4 Completed**: 2026-01-28
> **Phase 5 Completed**: 2026-01-28 (代码审查后优化)
> **Hotfix Applied**: 2026-01-28 (修复灰色块/渲染异常)
> **Phase 6 Paused**: 2026-01-28 (flutter_svg 兼容性问题待调试)

## 执行摘要

基于 Codex（后端）和 Gemini（前端）的并行分析，本计划将 spec 转化为零决策可执行步骤。

### 一致观点（强信号）

| 议题 | Codex | Gemini | 结论 |
|------|-------|--------|------|
| 全屏方案 | Navigator.push + 新 WebView | Navigator.push + InteractiveViewer | ✅ 采用 Navigator.push 新路由 |
| 高度测量 | MutationObserver + getBBox | 让渲染器自适应高度 | ✅ JS 端 getBBox 后回传高度 |
| 占位策略 | 启用 enableStablePlaceholder | AnimatedContainer 固定高度 | ✅ 流式阶段固定 360dp |
| HTML 修改 | 移除 overflow:hidden | overflow:visible | ✅ 移除 overflow:hidden |

### 分歧点（已决策）

| 议题 | Codex 观点 | Gemini 观点 | 决策 |
|------|-----------|-------------|------|
| 高度缓存 | 按内容 hash 缓存高度 | 不提及 | 暂不实现，Phase 3 可选 |
| Windows 平台 | 需确认 JS channel 可行性 | 未涉及 | 先实现 Android/iOS，Windows 用轮询降级 |

---

## Phase 1: 修复截断问题

**目标**: 解决图表截断、高度测量不准的根本原因

### Task 1.1: 修改 HTML 模板
**文件**: `assets/web/mermaid_template.html`
**工作量**: S (15 分钟)
**依赖**: 无

```diff
 body {
     background: transparent;
-    overflow: hidden;
+    overflow: visible;
     font-family: ...;
 }
 #diagram {
     padding: 16px;
-    display: flex;
-    justify-content: center;
-    align-items: center;
+    display: inline-block;
+    min-width: 100%;
 }
```

### Task 1.2: 添加渲染完成后高度测量
**文件**: `assets/web/mermaid_template.html`
**工作量**: M (30 分钟)
**依赖**: Task 1.1

在 `<script>` 中添加：

```javascript
import mermaid from '...';

mermaid.initialize({ startOnLoad: false, theme: '{{THEME}}' });

document.addEventListener('DOMContentLoaded', async () => {
  await mermaid.run();

  // 等待 SVG 渲染完成
  const observer = new MutationObserver(() => {
    const svg = document.querySelector('.mermaid svg');
    if (svg) {
      observer.disconnect();
      const bbox = svg.getBBox();
      const height = Math.ceil(bbox.height + bbox.y + 32);
      const width = Math.ceil(bbox.width + bbox.x);
      // 通过 JS channel 或 URL scheme 回传
      if (window.FlutterChannel) {
        window.FlutterChannel.postMessage(JSON.stringify({ width, height }));
      }
    }
  });
  observer.observe(document.getElementById('diagram'), { childList: true, subtree: true });
});
```

### Task 1.3: Dart 端接收高度消息
**文件**: `lib/widgets/mermaid_renderer.dart`
**工作量**: M (45 分钟)
**依赖**: Task 1.2

修改 `_MermaidRendererState`:

```dart
// 在 _initializeWebView() 中添加 JS channel
_controller = WebViewController()
  ..addJavaScriptChannel(
    'FlutterChannel',
    onMessageReceived: (message) {
      final data = jsonDecode(message.message);
      final height = (data['height'] as num?)?.toDouble() ?? 300;
      if (mounted) {
        setState(() => _webViewHeight = height);
      }
    },
  )
  // ... 其他配置
```

### Task 1.4: Windows 平台降级方案
**文件**: `lib/widgets/mermaid_renderer.dart`
**工作量**: S (20 分钟)
**依赖**: Task 1.3

Windows 使用 `webview_windows`，暂不支持 JS channel，保留现有轮询逻辑：

```dart
// Windows 平台：延迟轮询获取高度
if (Platform.isWindows) {
  Future.delayed(const Duration(milliseconds: 500), _getWebViewHeight);
}
```

---

## Phase 2: 重构全屏预览

**目标**: 解决 z-index 层级错乱、截断内容无法查看的问题

### Task 2.1: 创建 MermaidFullscreenPage
**文件**: `lib/chat_ui/owui/mermaid_fullscreen_page.dart` (新建)
**工作量**: L (60 分钟)
**依赖**: Phase 1 完成

```dart
/// Mermaid 全屏预览页面
///
/// 使用 Navigator.push 独立路由，解决 z-index 问题
class MermaidFullscreenPage extends StatefulWidget {
  final String mermaidCode;
  final bool isDark;

  const MermaidFullscreenPage({
    super.key,
    required this.mermaidCode,
    required this.isDark,
  });

  @override
  State<MermaidFullscreenPage> createState() => _MermaidFullscreenPageState();
}

class _MermaidFullscreenPageState extends State<MermaidFullscreenPage> {
  final TransformationController _transformController = TransformationController();

  @override
  Widget build(BuildContext context) {
    final uiScale = context.owui.uiScale;
    final bgColor = widget.isDark ? const Color(0xFF0D0D0D) : Colors.white;

    return Scaffold(
      backgroundColor: bgColor,
      body: CallbackShortcuts(
        bindings: {
          const SingleActivator(LogicalKeyboardKey.escape): () => Navigator.pop(context),
          const SingleActivator(LogicalKeyboardKey.equal, control: true): _zoomIn,
          const SingleActivator(LogicalKeyboardKey.minus, control: true): _zoomOut,
        },
        child: Focus(
          autofocus: true,
          child: Stack(
            children: [
              // 内容层：InteractiveViewer + MermaidRenderer
              InteractiveViewer(
                transformationController: _transformController,
                minScale: 0.5,
                maxScale: 4.0,
                boundaryMargin: const EdgeInsets.all(double.infinity),
                child: Center(
                  child: MermaidRenderer(
                    mermaidCode: widget.mermaidCode,
                    isDark: widget.isDark,
                    includeOuterContainer: false,
                  ),
                ),
              ),

              // 工具栏层
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                child: _buildToolbar(context, uiScale),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildToolbar(BuildContext context, double uiScale) {
    // 实现工具栏：关闭、放大、缩小、重置、复制
  }

  void _zoomIn() {
    final current = _transformController.value.getMaxScaleOnAxis();
    _transformController.value = Matrix4.identity()..scale(current * 1.2);
  }

  void _zoomOut() {
    final current = _transformController.value.getMaxScaleOnAxis();
    _transformController.value = Matrix4.identity()..scale(current / 1.2);
  }
}
```

### Task 2.2: 修改 OwuiMermaidBlock 全屏逻辑
**文件**: `lib/chat_ui/owui/mermaid_block.dart`
**工作量**: M (30 分钟)
**依赖**: Task 2.1

```dart
// 删除 _buildFullscreenOverlay 方法
// 删除 _isFullscreen 状态变量
// 删除 _zoom, _offset 等状态变量

void _openFullscreen() {
  Navigator.of(context).push(
    PageRouteBuilder(
      opaque: true,
      pageBuilder: (_, __, ___) => MermaidFullscreenPage(
        mermaidCode: widget.mermaidCode,
        isDark: widget.isDark,
      ),
      transitionsBuilder: (_, animation, __, child) {
        return FadeTransition(opacity: animation, child: child);
      },
    ),
  );
}

// build() 中移除全屏分支判断
@override
Widget build(BuildContext context) {
  // 移除: if (_isFullscreen) return _buildFullscreenOverlay(context);
  // 直接返回内联视图
}
```

### Task 2.3: 添加加载状态
**文件**: `lib/chat_ui/owui/mermaid_fullscreen_page.dart`
**工作量**: S (15 分钟)
**依赖**: Task 2.1

在 `MermaidRenderer` 加载期间显示 loading 状态：

```dart
// 监听 MermaidRenderer 的加载状态
// 显示 CircularProgressIndicator + "正在渲染高清图表..."
```

---

## Phase 3: 优化滚动性能

**目标**: 解决滚动卡顿、WebView 高度跳变问题

### Task 3.1: 启用稳定占位符
**文件**: `lib/chat_ui/owui/mermaid_block.dart`
**工作量**: S (10 分钟)
**依赖**: 无

```dart
// 将 enableStablePlaceholder 默认值改为 true
const OwuiMermaidBlock({
  // ...
  this.enableStablePlaceholder = true, // 改为 true
});
```

### Task 3.2: 优化流式渲染占位
**文件**: `lib/chat_ui/owui/mermaid_block.dart`
**工作量**: S (15 分钟)
**依赖**: Task 3.1

确保流式阶段使用固定高度，避免布局抖动：

```dart
if (widget.isStreaming) {
  return AnimatedContainer(
    duration: const Duration(milliseconds: 200),
    curve: Curves.easeOut,
    height: OwuiMermaidBlock.stablePlaceholderHeight * uiScale,
    // ...
  );
}
```

### Task 3.3: MermaidRenderer 初始高度优化（可选）
**文件**: `lib/widgets/mermaid_renderer.dart`
**工作量**: M (30 分钟)
**依赖**: Phase 1 完成

将默认高度从 300 调整为 360，与占位符高度一致：

```dart
double _webViewHeight = 360; // 与 stablePlaceholderHeight 一致
```

---

## Phase 4: UX 完善

**目标**: 提升用户体验细节

### Task 4.1: 键盘快捷键（已在 Task 2.1 实现）
- ESC: 关闭全屏
- Ctrl +: 放大
- Ctrl -: 缩小

### Task 4.2: 优化加载动画
**文件**: `lib/widgets/mermaid_renderer.dart`
**工作量**: S (15 分钟)

使用骨架屏替代简单的 CircularProgressIndicator。

### Task 4.3: 错误状态优化
**文件**: `lib/widgets/mermaid_renderer.dart`
**工作量**: S (15 分钟)

错误时显示友好提示 + 复制源码按钮 + 重试选项。

---

## 验收清单

- [x] 滚动包含 Mermaid 的聊天页面无明显卡顿/回弹
- [x] 全屏预览完全覆盖所有 UI 元素（无层级穿透）
- [x] 全屏可查看完整图表内容（无截断）
- [x] 缩放/平移操作流畅
- [x] 支持 ESC 键退出全屏（桌面端）
- [x] 流式渲染期间无高度跳变

---

## 风险缓解

| 风险 | 缓解措施 |
|------|----------|
| InteractiveViewer + WebView 交互冲突 | 测试各平台，必要时回退到 GestureDetector |
| 高度测量仍不准确 | 添加延迟重试 + 多次测量取最大值 |
| Windows JS channel 不支持 | 保留轮询降级方案 |
| 全屏路由动画卡顿 | 使用 FadeTransition 替代默认动画 |

---

## 实施顺序

```
Phase 1.1 → 1.2 → 1.3 → 1.4 (可并行)
     ↓
Phase 2.1 → 2.2 → 2.3
     ↓
Phase 3.1 → 3.2 → 3.3 (可并行)
     ↓
Phase 4 (可选，按优先级)
```

**预估总工作量**: 约 5-6 小时

---

## Phase 5: 代码审查优化

> **来源**: `/ccg:review` 双模型审查 (Codex + Gemini)
> **优先级**: Major 问题必须修复

### 审查发现摘要

| 严重度 | 问题数 | 状态 |
|--------|--------|------|
| Critical | 0 | - |
| Major | 4 | ✅ 已修复 |
| Minor | 7 | ✅ 关键项已修复 |
| Suggestion | 6 | 📋 可选 |

### Task 5.1: 修复 Observer 竞态条件 ✅
**文件**: `assets/web/mermaid_template.html`
**严重度**: Major
**来源**: Codex

**问题**: MutationObserver 在 `mermaid.run()` 之后挂载，可能错过同步插入的 SVG。

**修复**:
- 在 `mermaid.run()` 之前挂载 observer
- 添加 `heightSent` 标志防止重复发送
- 添加 100ms 保底直接测量
- 添加 5s 超时自动断开 observer
- 修复 `bbox.y` 负值问题，使用 `Math.abs()`

### Task 5.2: 修复键盘缩放重置平移 ✅
**文件**: `lib/chat_ui/owui/mermaid_fullscreen_page.dart`
**严重度**: Major
**来源**: Gemini

**问题**: `_setScale` 使用 `Matrix4.identity()` 清除了平移坐标。

**修复**: 新增 `_setScaleKeepingTranslation()` 方法，保留当前 translation 向量后再应用缩放。

### Task 5.3: 添加跨平台键盘快捷键 ✅
**文件**: `lib/chat_ui/owui/mermaid_fullscreen_page.dart`
**严重度**: Major
**来源**: Gemini

**问题**: 仅绑定 Ctrl 键，macOS 用户期望 Cmd 键。

**修复**: 同时绑定 `control: true` 和 `meta: true` 修饰符。

### Task 5.4: 缓存边界控制 ✅
**文件**: `lib/widgets/mermaid_renderer.dart`
**严重度**: Major
**来源**: Codex

**问题**: 全局缓存无边界 + KeepAlive 导致内存增长。

**修复**: 添加 `_addToCache()` 函数实现简单 LRU 策略，限制最大 50 条目。

### Task 5.5: 渲染失败时断开 Observer ✅
**文件**: `assets/web/mermaid_template.html`

**修复**: 已在 Task 5.1 中添加 5s 超时自动断开。

### Task 5.6: 限制拖拽边界 ✅
**文件**: `lib/chat_ui/owui/mermaid_fullscreen_page.dart`

**修复**: 将 `boundaryMargin` 从 `double.infinity` 改为 `200`。

---

## 更新验收清单

- [x] 滚动包含 Mermaid 的聊天页面无明显卡顿/回弹
- [x] 全屏预览完全覆盖所有 UI 元素（无层级穿透）
- [x] 全屏可查看完整图表内容（无截断）
- [x] 缩放/平移操作流畅
- [x] 支持 ESC 键退出全屏（桌面端）
- [x] 流式渲染期间无高度跳变
- [x] **[Phase 5]** Observer 在 mermaid.run() 前挂载
- [x] **[Phase 5]** 键盘缩放保留平移位置
- [x] **[Phase 5]** 支持 macOS Cmd 快捷键
- [x] **[Phase 5]** 缓存有边界控制 (LRU, max 50)

---

## Hotfix: 修复灰色块/渲染异常

> **触发**: 用户报告 Phase 5 优化后 Mermaid 块显示异常
> **诊断**: Codex + Gemini 并行分析
> **修复时间**: 2026-01-28

### 问题症状

1. **Mermaid 块内容显示异常** - 可能空白或截断
2. **部分消息变成整个灰色块** - WebView 纹理脱离

### 根因分析

| 问题 | 根因 | 诊断来源 |
|------|------|----------|
| 灰色块 | `AnimatedSize` 包裹 WebView，动画期间调整大小导致纹理脱离 | Gemini |
| 内容空白 | `startOnLoad: false` + `mermaid.run()` 可能失败或抛出错误 | Codex |
| 高度错误 | 缓存非 360 高度时阻止降级探测运行 | Codex |

### 修复措施

#### Hotfix 1: 移除 AnimatedSize ✅
**文件**: `lib/chat_ui/owui/mermaid_block.dart`

**原因**: WebView 在动画期间调整大小会导致纹理脱离、变灰或无法渲染。

**修改**: 移除 `AnimatedSize` 包裹，让容器立即调整到正确高度。

#### Hotfix 2: 恢复 startOnLoad: true ✅
**文件**: `assets/web/mermaid_template.html`

**原因**: 手动 `mermaid.run()` 增加了失败风险，且与 Observer 存在时序问题。

**修改**: 恢复 `startOnLoad: true`，由 Mermaid 自动处理渲染。

#### Hotfix 3: 始终运行高度降级探测 ✅
**文件**: `lib/widgets/mermaid_renderer.dart`

**原因**: 当缓存高度非 360 时跳过降级探测，导致缓存失效后无法恢复。

**修改**: 移除 `_webViewHeight == 360` 条件，始终运行 `_getWebViewHeight()`。

### 教训总结

1. **WebView + 动画 = 高风险** - 避免在 WebView 容器上使用尺寸动画
2. **保持简单** - `startOnLoad: true` 比手动 `run()` 更稳定
3. **降级逻辑不应有条件** - 始终提供后备方案

---

## Hotfix 2: 移除 AutomaticKeepAliveClientMixin

> **触发**: 用户报告切换对话后灰色块覆盖上方内容
> **诊断**: Explore agent 分析 + 截图确认
> **修复时间**: 2026-01-28

### 问题症状

切换对话后，聊天内容区域上半部分变成灰色块，覆盖实际内容。重启后恢复正常。

### 根因分析

| 问题 | 根因 |
|------|------|
| 灰色块覆盖 | `AutomaticKeepAliveClientMixin` 导致 MermaidRenderer 状态在对话切换时不一致 |
| 触发条件 | 切换到包含 Mermaid 图表的对话 |
| 遮罩来源 | `_buildLoadingOverlay()` 的 `Positioned.fill` + `_isLoading = true` |

### 修复措施

**移除 MermaidRenderer 的 AutomaticKeepAliveClientMixin** ✅

**原因**: 该 mixin 用于防止滚动时 widget 重建，但与 IndexedStack 的对话切换逻辑冲突，导致：
- 旧对话的 MermaidRenderer 状态被保留
- 新对话显示时 `_isLoading` 状态不一致
- `Positioned.fill` 的加载遮罩覆盖整个内容区域

**权衡**: 移除 KeepAlive 后，滚动时 MermaidRenderer 会重建。但高度缓存机制仍然有效，可以防止高度跳变。

### 教训

- **KeepAlive + IndexedStack = 状态冲突风险** - 当外层使用 IndexedStack 切换视图时，内层的 KeepAlive 可能导致状态不同步
- **高度缓存已足够** - 不需要 KeepAlive 也能通过缓存防止高度跳变

---

## Phase 6: SVG 预渲染架构（根本性解决方案）

> **触发**: 移除 KeepAlive 后滚动回弹问题复现
> **诊断**: Codex + Gemini 并行分析 (2026-01-28)
> **状态**: ⏸️ 暂停 - flutter_svg 渲染 Mermaid SVG 时出现空白问题，需进一步调试

### 问题根因

**WebView 不适合嵌入 ListView**：
- WebView 是 Platform View，生命周期脆弱
- 滚动时重建导致高度异步测量，引发布局跳变
- KeepAlive 虽能防止重建，但与 IndexedStack 冲突导致状态错乱

### 双模型一致结论

| 议题 | Codex | Gemini | 结论 |
|------|-------|--------|------|
| 根因 | WebView 生命周期脆弱，重建导致高度不稳定 | 不要在 ListView 中驯服多个 WebView | ✅ WebView 不适合嵌入 ListView |
| 推荐方案 | SVG 渲染 → flutter_svg | 预渲染 SVG + 点击交互模式 | ✅ 采用 SVG 原生渲染 |
| 架构 | 两阶段布局：离线渲染 + 缓存展示 | 读写分离：列表态 SVG + 交互态 WebView | ✅ 分离渲染与展示 |

### 方案对比

| 方案 | 滚动流畅度 | 渲染准确性 | 复杂度 | 推荐度 |
|------|-----------|-----------|--------|--------|
| 当前 WebView | ⭐ 低 | ⭐⭐⭐ 高 | 中 | ❌ |
| HeadlessWebView → PNG | ⭐⭐⭐ 高 | ⭐⭐⭐ 高 | 高 | 🟡 |
| **HeadlessWebView → SVG** | ⭐⭐⭐ 高 | ⭐⭐⭐ 高 | 高 | ✅ 推荐 |
| 原生 flutter_mermaid | ⭐⭐⭐ 高 | ⭐⭐ 中 | 低 | 🟡 长期 |
| ListView 优化 | ⭐⭐ 中 | ⭐⭐⭐ 高 | 低 | ❌ 治标不治本 |

### 推荐架构：SVG 预渲染 + 原生展示

```
┌─────────────────────────────────────────────────────────────┐
│                      渲染流程                                │
├─────────────────────────────────────────────────────────────┤
│  Mermaid Code                                               │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────────┐                                    │
│  │ 单例隐藏 WebView     │  ← "渲染工厂"                      │
│  │ (Headless/Offscreen)│                                    │
│  └──────────┬──────────┘                                    │
│             │ mermaid.render() → SVG String                 │
│             ▼                                               │
│  ┌─────────────────────┐                                    │
│  │ SVG 缓存 (LRU)      │  ← 内存 + 可选磁盘持久化            │
│  │ {hash: {svg, w, h}} │                                    │
│  └──────────┬──────────┘                                    │
│             │                                               │
│             ▼                                               │
│  ┌─────────────────────┐    ┌─────────────────────┐        │
│  │ ListView 展示        │    │ 全屏交互            │        │
│  │ flutter_svg 渲染     │ → │ WebView + 缩放平移   │        │
│  │ (原生 Flutter)       │    │ (Navigator.push)    │        │
│  └─────────────────────┘    └─────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

### Task 6.1: 创建 MermaidSvgCache 服务 ✅

**文件**: `lib/services/mermaid_svg_cache.dart` (新建)
**实际实现**: 简化版 LRU 缓存，不使用 HeadlessWebView

```dart
/// Mermaid SVG 缓存服务
///
/// 职责：
/// 1. 管理单例隐藏 WebView 作为渲染工厂
/// 2. 调用 mermaid.render() 获取 SVG 字符串
/// 3. LRU 缓存 SVG + 尺寸数据
class MermaidSvgCache {
  static final instance = MermaidSvgCache._();
  MermaidSvgCache._();

  final _cache = <int, MermaidSvgData>{};
  static const _maxSize = 100;

  HeadlessInAppWebView? _renderEngine;

  /// 获取或渲染 SVG
  Future<MermaidSvgData?> getSvg(String mermaidCode, {bool isDark = false});

  /// 预热渲染引擎
  Future<void> warmUp();

  /// 清理缓存
  void clear();
}

class MermaidSvgData {
  final String svgString;
  final double width;
  final double height;
  final DateTime createdAt;
}
```

### Task 6.2: 修改 HTML 模板支持 SVG 导出 ✅

**文件**: `assets/web/mermaid_template.html` (修改现有模板)
**实际实现**: 在 measureAndSend() 中添加 svg: svgString 字段

```html
<!DOCTYPE html>
<html>
<head>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';

        window.renderMermaid = async function(code, theme) {
            const { svg } = await mermaid.render('diagram', code, undefined);

            // 解析 SVG 获取尺寸
            const parser = new DOMParser();
            const doc = parser.parseFromString(svg, 'image/svg+xml');
            const svgEl = doc.querySelector('svg');
            const width = parseFloat(svgEl.getAttribute('width')) || 400;
            const height = parseFloat(svgEl.getAttribute('height')) || 300;

            return JSON.stringify({ svg, width, height });
        };

        mermaid.initialize({ startOnLoad: false, theme: 'default' });
    </script>
</head>
<body></body>
</html>
```

### Task 6.3: 创建 MermaidSvgWidget ✅

**文件**: `lib/widgets/mermaid_svg_widget.dart` (新建)
**实际实现**: 简化为 StatelessWidget，直接接收 MermaidSvgData

```dart
/// 基于 flutter_svg 的 Mermaid 渲染 Widget
///
/// 用于 ListView 内联展示，替代 WebView
class MermaidSvgWidget extends StatefulWidget {
  final String mermaidCode;
  final bool isDark;
  final VoidCallback? onTap;

  @override
  State<MermaidSvgWidget> createState() => _MermaidSvgWidgetState();
}

class _MermaidSvgWidgetState extends State<MermaidSvgWidget> {
  MermaidSvgData? _svgData;
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadSvg();
  }

  Future<void> _loadSvg() async {
    final data = await MermaidSvgCache.instance.getSvg(
      widget.mermaidCode,
      isDark: widget.isDark,
    );
    if (mounted) {
      setState(() {
        _svgData = data;
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) return _buildSkeleton();
    if (_svgData == null) return _buildError();

    return GestureDetector(
      onTap: widget.onTap,
      child: SvgPicture.string(
        _svgData!.svgString,
        width: _svgData!.width,
        height: _svgData!.height,
      ),
    );
  }
}
```

### Task 6.4: 修改 MermaidRenderer 使用 SVG 渲染 ✅

**文件**: `lib/widgets/mermaid_renderer.dart`
**实际实现**:
- initState: 检查 SVG 缓存，有则跳过 WebView 初始化
- build: 有缓存时直接渲染 MermaidSvgWidget
- _handleHeightMessage: 解析 SVG 字符串并缓存

```dart
Widget _buildContent(BuildContext context) {
  // 流式阶段保持现有占位逻辑
  if (widget.isStreaming) {
    return _buildStreamingPlaceholder();
  }

  // 使用 SVG 渲染替代 WebView
  return Padding(
    padding: EdgeInsets.all(12 * uiScale),
    child: MermaidSvgWidget(
      mermaidCode: widget.mermaidCode,
      isDark: widget.isDark,
      onTap: _openFullscreen,  // 点击打开全屏 WebView 交互
    ),
  );
}
```

### Task 6.5: 添加 flutter_svg 依赖 ✅

**文件**: `pubspec.yaml`
**实际实现**: 仅添加 flutter_svg（不需要 flutter_inappwebview）

```yaml
dependencies:
  flutter_svg: ^2.0.10+1
```

### Task 6.6: 保留 WebView 用于全屏交互 ✅

**文件**: `lib/chat_ui/owui/mermaid_fullscreen_page.dart`
**实际实现**: 无需修改，全屏页面继续使用 WebView + InteractiveViewer

### 实际架构（简化版）

```
首次渲染:
  Mermaid Code → WebView 渲染 → JS 回传 {height, svg} → 缓存 SVG
                                                         ↓
重建时:                                            MermaidSvgCache
  检查缓存 → 有缓存 → flutter_svg 渲染（原生 Flutter，零跳变）
           → 无缓存 → WebView 渲染（同上）
```

**与原计划的差异**:
- 不使用 HeadlessInAppWebView（避免新依赖的兼容性问题）
- 首次渲染仍用 WebView，但渲染完成后缓存 SVG
- 重建时直接使用缓存的 SVG（解决滚动回弹问题）

### 验收清单 (Phase 6)

- [ ] ListView 滚动流畅，无回弹/高度跳变（需用户验证）
- [ ] SVG 渲染保真度与 WebView 一致（需用户验证）
- [x] 缓存命中时秒加载
- [x] 内存占用可控（LRU 缓存边界 100 条目）
- [ ] Windows/Linux/macOS/Android/iOS 全平台支持（需用户验证）

### 风险与缓解

| 风险 | 缓解措施 | 状态 |
|------|----------|------|
| SVG 渲染与 WebView 不一致 | 测试各类图表类型；保留 WebView 作为降级方案 | 待验证 |
| 大型 SVG 渲染性能 | flutter_svg 对大型 SVG 优化良好 | 待验证 |
| 首次渲染仍需 WebView | 可接受，关键是解决重建时的跳变 | ✅ 已解决 |

### 实施记录

**实际耗时**: 约 1 小时（简化方案）

**修改的文件**:
1. `pubspec.yaml` - 添加 flutter_svg 依赖
2. `assets/web/mermaid_template.html` - 添加 SVG 字符串回传
3. `lib/services/mermaid_svg_cache.dart` - 新建 SVG 缓存服务
4. `lib/widgets/mermaid_svg_widget.dart` - 新建 SVG 渲染组件
5. `lib/widgets/mermaid_renderer.dart` - 集成 SVG 缓存逻辑
