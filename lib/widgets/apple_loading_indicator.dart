import 'package:flutter/material.dart';
import '../design_system/apple_tokens.dart';

/// Apple风格Loading指示器
/// 
/// 支持三种尺寸：small(16px), medium(24px), large(32px)
/// 带有平滑的旋转动画和渐变效果
class AppleLoadingIndicator extends StatefulWidget {
  final double? size;
  final Color? color;
  final double strokeWidth;

  const AppleLoadingIndicator({
    super.key,
    this.size,
    this.color,
    this.strokeWidth = 2.0,
  });

  /// 小尺寸 (16px)
  const AppleLoadingIndicator.small({
    super.key,
    Color? color,
  })  : size = 16.0,
        color = color,
        strokeWidth = 1.5;

  /// 中等尺寸 (24px)
  const AppleLoadingIndicator.medium({
    super.key,
    Color? color,
  })  : size = 24.0,
        color = color,
        strokeWidth = 2.0;

  /// 大尺寸 (32px)
  const AppleLoadingIndicator.large({
    super.key,
    Color? color,
  })  : size = 32.0,
        color = color,
        strokeWidth = 2.5;

  @override
  State<AppleLoadingIndicator> createState() => _AppleLoadingIndicatorState();
}

class _AppleLoadingIndicatorState extends State<AppleLoadingIndicator>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final size = widget.size ?? 24.0;
    final color = widget.color ?? AppleColors.blue;

    return RotationTransition(
      turns: _controller,
      child: CustomPaint(
        size: Size(size, size),
        painter: _AppleLoadingPainter(
          color: color,
          strokeWidth: widget.strokeWidth,
        ),
      ),
    );
  }
}

/// Apple风格Loading画笔
class _AppleLoadingPainter extends CustomPainter {
  final Color color;
  final double strokeWidth;

  _AppleLoadingPainter({
    required this.color,
    required this.strokeWidth,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width - strokeWidth) / 2;

    // 渐变圆弧
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round
      ..shader = SweepGradient(
        colors: [
          color.withValues(alpha: 0.0),
          color.withValues(alpha: 0.3),
          color.withValues(alpha: 0.6),
          color,
        ],
        stops: const [0.0, 0.3, 0.6, 1.0],
        transform: const GradientRotation(-1.5708), // -90度
      ).createShader(Rect.fromCircle(center: center, radius: radius));

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      0,
      6.2832, // 2π 完整圆弧
      false,
      paint,
    );
  }

  @override
  bool shouldRepaint(_AppleLoadingPainter oldDelegate) {
    return oldDelegate.color != color || oldDelegate.strokeWidth != strokeWidth;
  }
}

/// Apple风格脉冲Loading（用于按钮等场景）
class ApplePulsingDot extends StatefulWidget {
  final double size;
  final Color? color;

  const ApplePulsingDot({
    super.key,
    this.size = 8.0,
    this.color,
  });

  @override
  State<ApplePulsingDot> createState() => _ApplePulsingDotState();
}

class _ApplePulsingDotState extends State<ApplePulsingDot>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    )..repeat(reverse: true);

    _animation = Tween<double>(begin: 0.4, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? AppleColors.blue;

    return AnimatedBuilder(
      animation: _animation,
      builder: (context, child) {
        return Container(
          width: widget.size,
          height: widget.size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color.withValues(alpha: _animation.value),
            boxShadow: [
              BoxShadow(
                color: color.withValues(alpha: _animation.value * 0.3),
                blurRadius: widget.size * 0.8,
                spreadRadius: widget.size * 0.2,
              ),
            ],
          ),
        );
      },
    );
  }
}

/// Apple风格三点Loading（用于"正在输入"等场景）
class AppleTypingIndicator extends StatefulWidget {
  final double dotSize;
  final Color? color;
  final double spacing;

  const AppleTypingIndicator({
    super.key,
    this.dotSize = 8.0,
    this.color,
    this.spacing = 6.0,
  });

  @override
  State<AppleTypingIndicator> createState() => _AppleTypingIndicatorState();
}

class _AppleTypingIndicatorState extends State<AppleTypingIndicator>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1400),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? AppleColors.secondaryLabel(context);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(3, (index) {
        return Padding(
          padding: EdgeInsets.only(
            right: index < 2 ? widget.spacing : 0,
          ),
          child: _AnimatedDot(
            size: widget.dotSize,
            color: color,
            delay: index * 200,
            controller: _controller,
          ),
        );
      }),
    );
  }
}

class _AnimatedDot extends StatelessWidget {
  final double size;
  final Color color;
  final int delay;
  final AnimationController controller;

  const _AnimatedDot({
    required this.size,
    required this.color,
    required this.delay,
    required this.controller,
  });

  @override
  Widget build(BuildContext context) {
    final animation = Tween<double>(begin: 0.4, end: 1.0).animate(
      CurvedAnimation(
        parent: controller,
        curve: Interval(
          delay / 1400,
          (delay + 600) / 1400,
          curve: Curves.easeInOut,
        ),
      ),
    );

    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) {
        return Transform.translate(
          offset: Offset(0, -(size * 0.3) * (animation.value - 0.4) / 0.6),
          child: Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withValues(alpha: animation.value),
            ),
          ),
        );
      },
    );
  }
}
