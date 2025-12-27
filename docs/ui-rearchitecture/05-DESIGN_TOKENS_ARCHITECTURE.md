# 设计令牌架构设计

> 统一的主题系统设计，确保 flutter_chat_ui、shadcn_ui 和普通组件的样式一致性。

## 1. 现有设计系统分析

### 1.1 ChatBoxTokens (现有)

**文件**: `lib/design_system/design_tokens.dart`

```dart
class ChatBoxTokens {
  static const spacing = _Spacing();   // 基于 8px 网格
  static const radius = _Radius();     // 圆角系统
  static const elevation = _Elevation(); // 阴影系统
  static const animation = _Animation(); // 动画系统
  static const breakpoints = _Breakpoints(); // 响应式断点
}
```

**当前值**:
| Token | 值 | 用途 |
|-------|-----|------|
| `spacing.xs` | 4px | 极小间距 |
| `spacing.sm` | 8px | 小间距 |
| `spacing.md` | 12px | 中间距 |
| `spacing.lg` | 16px | 大间距 |
| `spacing.xl` | 24px | 超大间距 |
| `radius.small` | 8px | 小圆角 |
| `radius.medium` | 12px | 中圆角 |
| `radius.large` | 16px | 大圆角 |

### 1.2 AppleTokens (现有)

**文件**: `lib/design_system/apple_tokens.dart`

```dart
class AppleTokens {
  static const corners = _Corners();  // Apple 风格圆角
  static const shadows = _Shadows();  // Apple 风格阴影
}
```

**当前值**:
| Token | 值 | 用途 |
|-------|-----|------|
| `corners.bubble` | 20px | 气泡圆角 |
| `shadows.card` | 双层阴影 | 卡片阴影 |
| `shadows.bubble` | 双层阴影 | 气泡阴影 |

### 1.3 问题分析

1. **分散的样式定义**: `ChatBoxTokens` 和 `AppleTokens` 并存
2. **硬编码值**: 部分页面直接使用 `Colors.grey.shade600` 等
3. **主题不联动**: `flutter_chat_ui` 主题与 Material 主题分离
4. **颜色不统一**: 不同组件使用不同的颜色获取方式

---

## 2. 统一设计令牌架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     ThemeData (Material)                        │
│  └─ extensions: [ChatDesignTokens]                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ChatDesignTokens                             │
│  ├─ colors: ChatColorTokens                                     │
│  ├─ spacing: SpacingTokens                                      │
│  ├─ radius: RadiusTokens                                        │
│  ├─ animation: AnimationTokens                                  │
│  └─ typography: TypographyTokens                                │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ flutter_    │      │ shadcn_ui   │      │ 普通组件     │
│ chat_ui     │      │ 组件        │      │             │
│ ChatTheme   │      │ Component   │      │ 直接使用    │
│             │      │ Theme       │      │ Tokens      │
└─────────────┘      └─────────────┘      └─────────────┘
```

### 2.2 核心类设计

**文件**: `lib/design_system/chat_design_tokens.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_chat_ui/flutter_chat_ui.dart';

/// 统一设计令牌
/// 
/// 使用方法:
/// ```dart
/// final tokens = context.chatTokens;
/// final color = tokens.colors.bubblePrimary;
/// ```
class ChatDesignTokens extends ThemeExtension<ChatDesignTokens> {
  // ═══════════════════════════════════════════════════════════
  // 颜色令牌
  // ═══════════════════════════════════════════════════════════
  final ChatColorTokens colors;
  
  // ═══════════════════════════════════════════════════════════
  // 间距令牌
  // ═══════════════════════════════════════════════════════════
  final SpacingTokens spacing;
  
  // ═══════════════════════════════════════════════════════════
  // 圆角令牌
  // ═══════════════════════════════════════════════════════════
  final RadiusTokens radius;
  
  // ═══════════════════════════════════════════════════════════
  // 动画令牌
  // ═══════════════════════════════════════════════════════════
  final AnimationTokens animation;

  const ChatDesignTokens({
    required this.colors,
    required this.spacing,
    required this.radius,
    required this.animation,
  });

  /// Light 主题
  factory ChatDesignTokens.light() => ChatDesignTokens(
    colors: ChatColorTokens.light(),
    spacing: const SpacingTokens(),
    radius: const RadiusTokens(),
    animation: const AnimationTokens(),
  );

  /// Dark 主题
  factory ChatDesignTokens.dark() => ChatDesignTokens(
    colors: ChatColorTokens.dark(),
    spacing: const SpacingTokens(),
    radius: const RadiusTokens(),
    animation: const AnimationTokens(),
  );

  /// 转换为 flutter_chat_ui 主题
  ChatTheme toChatTheme() {
    return ChatTheme(
      colors: ChatColors(
        primary: colors.bubblePrimary,
        onPrimary: colors.onBubblePrimary,
        surface: colors.surface,
        onSurface: colors.textPrimary,
        surfaceContainerHigh: colors.bubbleSecondary,
        onSurfaceVariant: colors.textSecondary,
      ),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(radius.bubble),
      ),
    );
  }

  @override
  ChatDesignTokens copyWith({
    ChatColorTokens? colors,
    SpacingTokens? spacing,
    RadiusTokens? radius,
    AnimationTokens? animation,
  }) {
    return ChatDesignTokens(
      colors: colors ?? this.colors,
      spacing: spacing ?? this.spacing,
      radius: radius ?? this.radius,
      animation: animation ?? this.animation,
    );
  }

  @override
  ChatDesignTokens lerp(ChatDesignTokens? other, double t) {
    if (other == null) return this;
    return ChatDesignTokens(
      colors: colors.lerp(other.colors, t),
      spacing: spacing,
      radius: radius,
      animation: animation,
    );
  }
}
```

### 2.3 颜色令牌

```dart
/// 颜色令牌
class ChatColorTokens {
  // 气泡颜色
  final Color bubblePrimary;      // 用户气泡背景
  final Color onBubblePrimary;    // 用户气泡文字
  final Color bubbleSecondary;    // AI 气泡背景
  final Color onBubbleSecondary;  // AI 气泡文字
  
  // 思考气泡
  final Color thinkingBackground; // 思考气泡背景
  final Color thinkingBorder;     // 思考气泡边框
  
  // 表面颜色
  final Color surface;            // 页面背景
  final Color surfaceVariant;     // 次级背景
  
  // 文字颜色
  final Color textPrimary;        // 主要文字
  final Color textSecondary;      // 次要文字
  final Color textMuted;          // 静音文字
  
  // 强调颜色
  final Color accent;             // 强调色
  final Color destructive;        // 错误/删除色
  final Color success;            // 成功色
  final Color warning;            // 警告色

  const ChatColorTokens({
    required this.bubblePrimary,
    required this.onBubblePrimary,
    required this.bubbleSecondary,
    required this.onBubbleSecondary,
    required this.thinkingBackground,
    required this.thinkingBorder,
    required this.surface,
    required this.surfaceVariant,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.accent,
    required this.destructive,
    required this.success,
    required this.warning,
  });

  /// Apple 风格浅色主题
  factory ChatColorTokens.light() => const ChatColorTokens(
    bubblePrimary: Color(0xFF007AFF),
    onBubblePrimary: Color(0xFFFFFFFF),
    bubbleSecondary: Color(0xFFF2F2F7),
    onBubbleSecondary: Color(0xFF000000),
    thinkingBackground: Color(0xFFFFF9E6),
    thinkingBorder: Color(0xFFFFD60A),
    surface: Color(0xFFFFFFFF),
    surfaceVariant: Color(0xFFF2F2F7),
    textPrimary: Color(0xFF000000),
    textSecondary: Color(0xFF3C3C43),
    textMuted: Color(0xFF8E8E93),
    accent: Color(0xFF007AFF),
    destructive: Color(0xFFFF3B30),
    success: Color(0xFF34C759),
    warning: Color(0xFFFF9500),
  );

  /// Apple 风格深色主题
  factory ChatColorTokens.dark() => const ChatColorTokens(
    bubblePrimary: Color(0xFF0A84FF),
    onBubblePrimary: Color(0xFFFFFFFF),
    bubbleSecondary: Color(0xFF1C1C1E),
    onBubbleSecondary: Color(0xFFFFFFFF),
    thinkingBackground: Color(0xFF3D3520),
    thinkingBorder: Color(0xFFFFD60A),
    surface: Color(0xFF000000),
    surfaceVariant: Color(0xFF1C1C1E),
    textPrimary: Color(0xFFFFFFFF),
    textSecondary: Color(0xFFEBEBF5),
    textMuted: Color(0xFF8E8E93),
    accent: Color(0xFF0A84FF),
    destructive: Color(0xFFFF453A),
    success: Color(0xFF30D158),
    warning: Color(0xFFFF9F0A),
  );

  ChatColorTokens lerp(ChatColorTokens other, double t) {
    return ChatColorTokens(
      bubblePrimary: Color.lerp(bubblePrimary, other.bubblePrimary, t)!,
      onBubblePrimary: Color.lerp(onBubblePrimary, other.onBubblePrimary, t)!,
      bubbleSecondary: Color.lerp(bubbleSecondary, other.bubbleSecondary, t)!,
      onBubbleSecondary: Color.lerp(onBubbleSecondary, other.onBubbleSecondary, t)!,
      thinkingBackground: Color.lerp(thinkingBackground, other.thinkingBackground, t)!,
      thinkingBorder: Color.lerp(thinkingBorder, other.thinkingBorder, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      surfaceVariant: Color.lerp(surfaceVariant, other.surfaceVariant, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      textMuted: Color.lerp(textMuted, other.textMuted, t)!,
      accent: Color.lerp(accent, other.accent, t)!,
      destructive: Color.lerp(destructive, other.destructive, t)!,
      success: Color.lerp(success, other.success, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
    );
  }
}
```

### 2.4 间距令牌

```dart
/// 间距令牌 (基于 8px 网格)
class SpacingTokens {
  final double xs;   // 4px
  final double sm;   // 8px
  final double md;   // 12px
  final double lg;   // 16px
  final double xl;   // 24px
  final double xxl;  // 32px

  const SpacingTokens({
    this.xs = 4.0,
    this.sm = 8.0,
    this.md = 12.0,
    this.lg = 16.0,
    this.xl = 24.0,
    this.xxl = 32.0,
  });

  /// 动态间距 (用于列表项等)
  double get itemPadding => md;
  double get sectionPadding => lg;
  double get pagePadding => lg;
  double get cardPadding => md;
  double get bubblePadding => md;
}
```

### 2.5 圆角令牌

```dart
/// 圆角令牌
class RadiusTokens {
  final double xs;      // 4px
  final double sm;      // 8px
  final double md;      // 12px
  final double lg;      // 16px
  final double bubble;  // 20px (Apple 风格气泡)
  final double full;    // 9999px (圆形)

  const RadiusTokens({
    this.xs = 4.0,
    this.sm = 8.0,
    this.md = 12.0,
    this.lg = 16.0,
    this.bubble = 20.0,
    this.full = 9999.0,
  });

  BorderRadius get bubbleBorderRadius => BorderRadius.circular(bubble);
  BorderRadius get cardBorderRadius => BorderRadius.circular(md);
  BorderRadius get buttonBorderRadius => BorderRadius.circular(sm);
}
```

### 2.6 动画令牌

```dart
/// 动画令牌
class AnimationTokens {
  final Duration fast;    // 150ms
  final Duration normal;  // 210ms (Apple 标准)
  final Duration slow;    // 300ms
  final Duration slower;  // 500ms

  final Curve standard;   // easeInOut
  final Curve enter;      // easeOut
  final Curve exit;       // easeIn

  const AnimationTokens({
    this.fast = const Duration(milliseconds: 150),
    this.normal = const Duration(milliseconds: 210),
    this.slow = const Duration(milliseconds: 300),
    this.slower = const Duration(milliseconds: 500),
    this.standard = Curves.easeInOut,
    this.enter = Curves.easeOut,
    this.exit = Curves.easeIn,
  });
}
```

---

## 3. 集成到应用

### 3.1 注册 ThemeExtension

**文件**: `lib/main.dart`

```dart
MaterialApp(
  theme: ThemeData(
    colorScheme: ColorScheme.fromSeed(
      seedColor: Colors.blue,
      brightness: Brightness.light,
    ),
    extensions: [
      ChatDesignTokens.light(),
    ],
  ),
  darkTheme: ThemeData(
    colorScheme: ColorScheme.fromSeed(
      seedColor: Colors.blue,
      brightness: Brightness.dark,
    ),
    extensions: [
      ChatDesignTokens.dark(),
    ],
  ),
)
```

### 3.2 便捷访问扩展

```dart
extension ChatDesignTokensExt on BuildContext {
  ChatDesignTokens get chatTokens => 
      Theme.of(this).extension<ChatDesignTokens>() ?? 
      ChatDesignTokens.light();
  
  ChatColorTokens get chatColors => chatTokens.colors;
  SpacingTokens get chatSpacing => chatTokens.spacing;
  RadiusTokens get chatRadius => chatTokens.radius;
  AnimationTokens get chatAnimation => chatTokens.animation;
}
```

### 3.3 使用示例

```dart
class MyWidget extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final tokens = context.chatTokens;
    
    return Container(
      padding: EdgeInsets.all(tokens.spacing.md),
      decoration: BoxDecoration(
        color: tokens.colors.bubbleSecondary,
        borderRadius: tokens.radius.cardBorderRadius,
      ),
      child: Text(
        'Hello',
        style: TextStyle(color: tokens.colors.textPrimary),
      ),
    );
  }
}
```

---

## 4. 与 flutter_chat_ui 集成

### 4.1 自动同步主题

```dart
class ConversationViewV2 extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final tokens = context.chatTokens;
    final chatTheme = tokens.toChatTheme();
    
    return Chat(
      theme: chatTheme,
      // ...
    );
  }
}
```

### 4.2 主题变化响应

当用户切换明暗主题时，`ChatDesignTokens` 会自动从 `Theme.of(context)` 获取对应版本，`toChatTheme()` 会生成匹配的 `ChatTheme`。

---

## 5. 与 shadcn_ui 集成 (未来)

### 5.1 适配方案

```dart
// 将 ChatDesignTokens 映射到 shadcn_ui 主题
ComponentTheme<ButtonTheme>(
  data: ButtonTheme(
    primaryColor: context.chatColors.accent,
    borderRadius: context.chatRadius.sm,
  ),
  child: ShadcnButton(...),
)
```

### 5.2 统一组件包装

```dart
class ChatBoxButton extends StatelessWidget {
  final VoidCallback onPressed;
  final Widget child;
  
  @override
  Widget build(BuildContext context) {
    final tokens = context.chatTokens;
    
    return ElevatedButton(
      onPressed: onPressed,
      style: ElevatedButton.styleFrom(
        backgroundColor: tokens.colors.accent,
        foregroundColor: tokens.colors.onBubblePrimary,
        shape: RoundedRectangleBorder(
          borderRadius: tokens.radius.buttonBorderRadius,
        ),
        padding: EdgeInsets.symmetric(
          horizontal: tokens.spacing.lg,
          vertical: tokens.spacing.sm,
        ),
      ),
      child: child,
    );
  }
}
```

---

## 6. 迁移现有代码

### 6.1 替换硬编码颜色

**Before**:
```dart
Container(
  color: Colors.grey.shade300,
)
```

**After**:
```dart
Container(
  color: context.chatColors.surfaceVariant,
)
```

### 6.2 替换硬编码间距

**Before**:
```dart
Padding(
  padding: EdgeInsets.all(16),
)
```

**After**:
```dart
Padding(
  padding: EdgeInsets.all(context.chatSpacing.lg),
)
```

### 6.3 替换硬编码圆角

**Before**:
```dart
BorderRadius.circular(12)
```

**After**:
```dart
context.chatRadius.cardBorderRadius
```

---

## 7. 验证清单

- [ ] Light 主题颜色正确
- [ ] Dark 主题颜色正确
- [ ] flutter_chat_ui 主题同步
- [ ] 所有页面使用 Tokens
- [ ] 无硬编码样式值
- [ ] 主题切换无闪烁
- [ ] 动画时长一致

---

*文档版本: 1.0*
*创建时间: 2024-12-21*
