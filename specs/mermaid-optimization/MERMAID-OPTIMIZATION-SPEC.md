# OpenSpec: Mermaid 块性能优化与全屏预览重构

> **Status**: DRAFT
> **Created**: 2026-01-28
> **Author**: Claude (CCG Spec-Research)

## 1. 问题定义

### 1.1 用户报告的问题

| 问题 | 严重度 | 表现 |
|------|--------|------|
| **滚动卡顿** | 🔴 高 | 滚动到 Mermaid 区域前出现回弹和卡顿 |
| **全屏层级错乱** | 🔴 高 | 全屏预览时上方 UI 在图之下，下方 UI 在图之上 |
| **图表截断** | 🔴 高 | 部分图表只显示局部，全屏只能操作显示部分 |

### 1.2 根因分析

#### A. 滚动性能问题
- **直接原因**：WebView 初始化时使用硬编码 `_webViewHeight = 300`，渲染完成后跳变到实际高度
- **底层原因**：Flutter 平台视图在滚动列表中的性能开销 + 异步高度变化导致列表几何重计算
- **代码位置**：`lib/widgets/mermaid_renderer.dart:42`

#### B. 全屏层级问题
- **直接原因**：`_isFullscreen` 状态只是原地渲染不同 Widget，未脱离父级 Widget 树
- **底层原因**：平台视图（WebView）无法被 Flutter Widget 正确覆盖/裁剪
- **代码位置**：`lib/chat_ui/owui/mermaid_block.dart:429` - `if (_isFullscreen) return _buildFullscreenOverlay(context);`

#### C. 图表截断问题
- **直接原因**：`Transform.scale` 只缩放已裁剪的纹理，不会揭示更多内容
- **底层原因**：
  1. HTML 模板 `overflow: hidden` 限制内容
  2. 高度测量 `scrollHeight` 可能在 Mermaid 渲染完成前执行
  3. 全屏复用同一个已裁剪的 WebView 实例
- **代码位置**：`assets/web/mermaid_template.html:21`

## 2. 约束集

### 2.1 硬约束（MUST）

| ID | 约束 | 理由 |
|----|------|------|
| C1 | 全屏预览必须使用 `Navigator.push` 新路由 | 解决 Z-index 问题，保证覆盖所有内容 |
| C2 | 全屏 WebView 必须是新实例，非复用内联实例 | 避免继承内联视图的尺寸限制 |
| C3 | 移除 HTML 模板中的 `overflow: hidden` | 允许内容完整渲染 |
| C4 | 高度测量必须在 Mermaid 渲染完成后执行 | 获取准确的内容高度 |
| C5 | 滚动列表中 WebView 必须有稳定的占位高度 | 避免高度跳变导致滚动抖动 |

### 2.2 软约束（SHOULD）

| ID | 约束 | 理由 |
|----|------|------|
| S1 | 全屏交互应使用 `InteractiveViewer` | Flutter 原生缩放控制更可靠 |
| S2 | 考虑延迟加载 WebView（viewport 附近才初始化） | 减少平台视图数量提升性能 |
| S3 | 流式渲染期间应显示稳定占位符 | 避免内容抖动 |
| S4 | 全屏应支持键盘快捷键（ESC 退出，+/- 缩放） | 桌面端 UX 优化 |

### 2.3 非约束（WON'T）

| ID | 描述 | 理由 |
|----|------|------|
| W1 | 不替换 WebView 为 SVG 渲染 | 复杂度过高，Mermaid.js 依赖浏览器环境 |
| W2 | 不实现服务端预渲染 | 需要额外基础设施 |
| W3 | 不修改 flutter_chat_ui 核心逻辑 | 保持框架独立性 |

## 3. 技术方案

### 3.1 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                         Chat List                                │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 OwuiMermaidBlock                         │    │
│  │  ┌─────────────────────────────────────────────────┐    │    │
│  │  │  Inline View (Stable Height Placeholder)        │    │    │
│  │  │  - Fixed height during streaming                │    │    │
│  │  │  - MermaidRenderer (IgnorePointer) after done   │    │    │
│  │  └─────────────────────────────────────────────────┘    │    │
│  │  [Fullscreen Button] ──────┐                            │    │
│  └────────────────────────────│────────────────────────────┘    │
│                               │                                  │
└───────────────────────────────│──────────────────────────────────┘
                                │ Navigator.push
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  MermaidFullscreenPage (New Route)               │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Header: Title + Zoom Controls + Close Button           │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  InteractiveViewer                                      │    │
│  │  └── MermaidRenderer (NEW instance, unconstrained)      │    │
│  │      - Full content rendering                           │    │
│  │      - Native pan/zoom via InteractiveViewer            │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 关键改动

#### 3.2.1 HTML 模板修改
```html
<!-- Before -->
body {
    overflow: hidden;
}

<!-- After -->
body {
    overflow: visible;
}
#diagram {
    display: inline-block;  /* 允许内容撑开 */
    min-width: 100%;
}
```

#### 3.2.2 高度测量改进
```javascript
// 等待 Mermaid 渲染完成后测量 SVG 边界
mermaid.run().then(() => {
    const svg = document.querySelector('.mermaid svg');
    if (svg) {
        const bbox = svg.getBBox();
        const height = bbox.height + bbox.y + 32; // padding
        // 通过 JS channel 回传高度
    }
});
```

#### 3.2.3 全屏路由实现
```dart
class MermaidFullscreenPage extends StatefulWidget {
  final String mermaidCode;
  final bool isDark;
  // ...
}

// 打开方式
void _openFullscreen() {
  Navigator.of(context).push(
    MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => MermaidFullscreenPage(
        mermaidCode: widget.mermaidCode,
        isDark: widget.isDark,
      ),
    ),
  );
}
```

#### 3.2.4 稳定占位策略
```dart
// 流式渲染期间
if (widget.isStreaming) {
  return SizedBox(
    height: 360, // 固定高度
    child: _buildLoadingIndicator(),
  );
}

// 渲染完成后
return MermaidRenderer(
  height: _measuredHeight ?? 360, // 使用测量高度或默认值
  // ...
);
```

## 4. 实施计划

### Phase 1: 修复截断问题（优先级最高）
- [ ] 修改 `mermaid_template.html` 移除 `overflow: hidden`
- [ ] 改进高度测量逻辑，使用 SVG getBBox
- [ ] 添加 MutationObserver 监听渲染完成

### Phase 2: 重构全屏预览
- [ ] 创建 `MermaidFullscreenPage` 独立路由
- [ ] 使用 `InteractiveViewer` 实现缩放/平移
- [ ] 全屏创建新 WebView 实例
- [ ] 添加工具栏（缩放控制、重置、关闭）

### Phase 3: 优化滚动性能
- [ ] 启用稳定占位符 (`enableStablePlaceholder`)
- [ ] 考虑 viewport 附近才加载 WebView（懒加载）
- [ ] 测试不同设备上的性能

### Phase 4: UX 完善
- [ ] 添加键盘快捷键支持
- [ ] 优化加载动画
- [ ] 添加错误状态的用户友好提示

## 5. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| InteractiveViewer + WebView 交互冲突 | 中 | 中 | 测试各平台，必要时回退到 GestureDetector |
| 高度测量仍不准确 | 中 | 高 | 添加多次测量 + 最大值策略 |
| 全屏路由动画卡顿 | 低 | 低 | 使用 FadeTransition 替代默认动画 |

## 6. 验收标准

- [ ] 滚动包含 Mermaid 的聊天页面无明显卡顿/回弹
- [ ] 全屏预览完全覆盖所有 UI 元素（无层级穿透）
- [ ] 全屏可查看完整图表内容（无截断）
- [ ] 缩放/平移操作流畅
- [ ] 支持 ESC 键退出全屏（桌面端）

## 7. 网络调研发现

### 7.1 Mermaid 渲染方案对比

| 方案 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| **WebView 内嵌** | 当前实现 | 支持交互、实时渲染 | 性能差、平台视图限制 |
| **mermaid-cli** | 服务端/构建时预渲染 | 高质量 SVG/PNG、可 Docker 部署 | 需要 Node.js + Puppeteer |
| **flutter_svg** | 显示预渲染 SVG | 原生 Flutter、高性能 | 需要预先生成 SVG |

### 7.2 Mermaid API 关键发现

```javascript
// 编程方式获取 SVG 和准确尺寸
mermaid.initialize({ startOnLoad: false });
const { svg } = await mermaid.render('id', diagramDefinition);

// 使用 getBBox 获取准确尺寸（而非 scrollHeight）
const svgEl = document.querySelector('.mermaid svg');
const bbox = svgEl.getBBox();
const actualHeight = bbox.height + bbox.y + 32; // 加 padding
```

### 7.3 Flutter 滚动性能最佳实践

根据 Flutter 官方文档和社区实践：

1. **懒加载构建器**：使用 `ListView.builder`，只构建视口内的 Widget
2. **itemExtent 固定高度**：已知高度时提供固定值，避免布局计算
3. **平台视图限制**：WebView 等平台视图在滚动列表中性能较差，建议：
   - 使用占位符直到内容可见
   - 池化/复用 WebView 实例
   - 考虑静态图片预览 + 点击展开详情

### 7.4 推荐的混合策略

```
┌──────────────────────────────────────────────────────────┐
│                    Inline View (列表内)                   │
├──────────────────────────────────────────────────────────┤
│  1. 流式渲染中 → 固定高度占位符 (360dp)                    │
│  2. 渲染完成后 → WebView (IgnorePointer, 懒加载)          │
│  3. 点击全屏 → Navigator.push 新路由                      │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                Fullscreen Page (新路由)                   │
├──────────────────────────────────────────────────────────┤
│  1. 创建新 WebView 实例（无尺寸限制）                       │
│  2. InteractiveViewer 包裹实现缩放/平移                    │
│  3. 工具栏：缩放控制 + 复制 + 外部打开 + 关闭              │
└──────────────────────────────────────────────────────────┘
```

### 7.5 高度测量改进方案

**当前问题**：使用 `scrollHeight` 可能在渲染完成前返回错误值

**推荐方案**：
```javascript
// 等待 Mermaid 渲染完成后使用 getBBox
mermaid.run().then(() => {
  const svg = document.querySelector('.mermaid svg');
  if (svg) {
    const bbox = svg.getBBox();
    // 通过 JS channel 回传准确高度
    FlutterChannel.postMessage(JSON.stringify({
      width: bbox.width + bbox.x,
      height: bbox.height + bbox.y + 32
    }));
  }
});
```

## 8. 参考资料

- [Flutter Platform Views Performance](https://docs.flutter.dev/platform-integration/android/platform-views)
- [Flutter Performance Best Practices](https://docs.flutter.dev/perf/best-practices)
- [webview_flutter_android](https://pub.dev/packages/webview_flutter_android)
- [InteractiveViewer API](https://api.flutter.dev/flutter/widgets/InteractiveViewer-class.html)
- [mermaid-cli](https://github.com/mermaid-js/mermaid-cli) - 命令行渲染工具
- [Mermaid API Usage](https://mermaid.js.org/config/usage.html) - 编程式渲染
