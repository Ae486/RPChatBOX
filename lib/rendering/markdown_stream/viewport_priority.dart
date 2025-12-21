import 'package:flutter/material.dart';

/// 可见性句柄
/// 
/// 用于跟踪元素的可见性状态
class VisibilityHandle {
  /// 是否可见
  final ValueNotifier<bool> isVisible;

  /// 当元素变为可见时完成
  final Future<void> whenVisible;

  /// 清理函数
  final VoidCallback destroy;

  VisibilityHandle({
    required this.isVisible,
    required this.whenVisible,
    required this.destroy,
  });

  /// 创建一个立即可见的句柄（用于禁用模式）
  factory VisibilityHandle.immediate() {
    final notifier = ValueNotifier<bool>(true);
    return VisibilityHandle(
      isVisible: notifier,
      whenVisible: Future.value(),
      destroy: () => notifier.dispose(),
    );
  }
}

/// 视口优先级注册函数类型
typedef ViewportRegisterFn = VisibilityHandle Function(
  GlobalKey elementKey, {
  double? rootMargin,
  double? threshold,
});

/// 视口优先级提供器
/// 
/// 参考 markstream-vue 的 viewportPriority 机制
/// 用于延迟渲染视口外的复杂节点，优先渲染可见区域
class ViewportPriorityProvider extends InheritedWidget {
  /// 注册函数
  final ViewportRegisterFn register;

  /// 是否启用
  final bool enabled;

  const ViewportPriorityProvider({
    super.key,
    required this.register,
    required this.enabled,
    required super.child,
  });

  /// 获取最近的 ViewportPriorityProvider
  static ViewportPriorityProvider? maybeOf(BuildContext context) {
    return context.dependOnInheritedWidgetOfExactType<ViewportPriorityProvider>();
  }

  /// 获取注册函数，如果未找到则返回立即可见的 fallback
  static ViewportRegisterFn of(BuildContext context) {
    final provider = maybeOf(context);
    if (provider == null || !provider.enabled) {
      return _immediateFallback;
    }
    return provider.register;
  }

  static VisibilityHandle _immediateFallback(GlobalKey elementKey, {double? rootMargin, double? threshold}) {
    return VisibilityHandle.immediate();
  }

  @override
  bool updateShouldNotify(ViewportPriorityProvider oldWidget) {
    return enabled != oldWidget.enabled || register != oldWidget.register;
  }
}

/// 延迟渲染包装器
/// 
/// 在元素进入视口前显示占位符，进入后显示实际内容
class DeferredRenderWidget extends StatefulWidget {
  /// 实际内容构建器
  final WidgetBuilder builder;

  /// 占位符（可选）
  final Widget? placeholder;

  /// 占位符高度（用于保持布局稳定）
  final double? placeholderHeight;

  /// 视口边距（提前多少像素开始渲染）
  final double rootMargin;

  /// 是否启用延迟渲染
  final bool enabled;

  const DeferredRenderWidget({
    super.key,
    required this.builder,
    this.placeholder,
    this.placeholderHeight,
    this.rootMargin = 300,
    this.enabled = true,
  });

  @override
  State<DeferredRenderWidget> createState() => _DeferredRenderWidgetState();
}

class _DeferredRenderWidgetState extends State<DeferredRenderWidget> {
  final GlobalKey _elementKey = GlobalKey();
  VisibilityHandle? _handle;
  bool _shouldRender = false;

  @override
  void initState() {
    super.initState();
    if (!widget.enabled) {
      _shouldRender = true;
      return;
    }
    _registerVisibility();
  }

  void _registerVisibility() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      
      final register = ViewportPriorityProvider.of(context);
      _handle = register(
        _elementKey,
        rootMargin: widget.rootMargin,
      );

      _handle!.isVisible.addListener(_onVisibilityChanged);
      
      // 检查初始状态
      if (_handle!.isVisible.value && !_shouldRender) {
        setState(() => _shouldRender = true);
      }
    });
  }

  void _onVisibilityChanged() {
    if (_handle!.isVisible.value && !_shouldRender) {
      setState(() => _shouldRender = true);
    }
  }

  @override
  void dispose() {
    _handle?.isVisible.removeListener(_onVisibilityChanged);
    _handle?.destroy();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_shouldRender) {
      return KeyedSubtree(
        key: _elementKey,
        child: widget.builder(context),
      );
    }

    return KeyedSubtree(
      key: _elementKey,
      child: widget.placeholder ?? SizedBox(
        height: widget.placeholderHeight ?? 100,
        child: const Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      ),
    );
  }
}

/// 简化的视口检测 Mixin
/// 
/// 用于在 StatefulWidget 中检测视口可见性
mixin ViewportVisibilityMixin<T extends StatefulWidget> on State<T> {
  bool _isInViewport = false;
  bool get isInViewport => _isInViewport;

  VisibilityHandle? _visibilityHandle;

  /// 子类调用此方法注册视口检测
  void registerViewportVisibility(GlobalKey key, {double rootMargin = 300}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;

      final register = ViewportPriorityProvider.of(context);
      _visibilityHandle = register(key, rootMargin: rootMargin);

      _visibilityHandle!.isVisible.addListener(_onViewportVisibilityChanged);
      _isInViewport = _visibilityHandle!.isVisible.value;
    });
  }

  void _onViewportVisibilityChanged() {
    final newValue = _visibilityHandle!.isVisible.value;
    if (newValue != _isInViewport) {
      setState(() => _isInViewport = newValue);
      onViewportVisibilityChanged(newValue);
    }
  }

  /// 子类可重写此方法响应可见性变化
  void onViewportVisibilityChanged(bool isVisible) {}

  @override
  void dispose() {
    _visibilityHandle?.isVisible.removeListener(_onViewportVisibilityChanged);
    _visibilityHandle?.destroy();
    super.dispose();
  }
}
