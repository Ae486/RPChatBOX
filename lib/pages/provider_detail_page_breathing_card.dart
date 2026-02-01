/// INPUT: 动画状态
/// OUTPUT: _BreathingBorderCard - 呼吸边框卡片组件
/// POS: UI 层 / Pages / Provider Detail - 动画辅助组件

part of 'provider_detail_page.dart';

/// 呼吸边框卡片组件
class _BreathingBorderCard extends StatefulWidget {
  final Widget child;
  final EdgeInsetsGeometry margin;
  final bool isBreathing;
  final bool isSelected;

  const _BreathingBorderCard({
    required this.child,
    required this.margin,
    required this.isBreathing,
    required this.isSelected,
  });

  @override
  State<_BreathingBorderCard> createState() => _BreathingBorderCardState();
}

class _BreathingBorderCardState extends State<_BreathingBorderCard>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    );

    _animation = Tween<double>(begin: 0.3, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );

    if (widget.isBreathing) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void didUpdateWidget(_BreathingBorderCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isBreathing && !oldWidget.isBreathing) {
      _controller.repeat(reverse: true);
    } else if (!widget.isBreathing && oldWidget.isBreathing) {
      _controller.stop();
      _controller.value = 1.0;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;
    final scheme = Theme.of(context).colorScheme;
    final radius = context.owuiRadius.rXl;

    return AnimatedBuilder(
      animation: _animation,
      builder: (context, child) {
        final Color borderColor;
        final double borderWidth;

        if (widget.isSelected) {
          borderColor = scheme.primary;
          borderWidth = 1.5;
        } else if (widget.isBreathing) {
          borderColor = scheme.primary.withValues(alpha: _animation.value * 0.35);
          borderWidth = 1;
        } else {
          borderColor = colors.borderSubtle;
          borderWidth = 1;
        }

        return Container(
          margin: widget.margin,
          decoration: BoxDecoration(
            color: colors.surfaceCard,
            borderRadius: BorderRadius.circular(radius),
            border: Border.all(color: borderColor, width: borderWidth),
          ),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}
