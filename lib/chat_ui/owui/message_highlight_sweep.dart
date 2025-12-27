import 'package:flutter/material.dart';

class OwuiMessageHighlightSweep extends StatefulWidget {
  // Timeline: fade-in -> hold -> fade-out (no sweep/movement; overlay-only).
  static const defaultExpandDuration = Duration(milliseconds: 140);
  static const defaultHoldDuration = Duration(milliseconds: 420);
  static const defaultFadeOutDuration = Duration(milliseconds: 520);
  static const defaultMaxOpacity = 0.16;

  final Color color;
  final BorderRadius borderRadius;

  final Duration expandDuration;
  final Duration holdDuration;
  final Duration fadeOutDuration;

  final double maxOpacity;
  final Curve curve;

  const OwuiMessageHighlightSweep({
    super.key,
    required this.color,
    required this.borderRadius,
    this.expandDuration = defaultExpandDuration,
    this.holdDuration = defaultHoldDuration,
    this.fadeOutDuration = defaultFadeOutDuration,
    this.maxOpacity = defaultMaxOpacity,
    this.curve = Curves.easeOutCubic,
  });

  Duration get totalDuration =>
      expandDuration + holdDuration + fadeOutDuration;

  @override
  State<OwuiMessageHighlightSweep> createState() =>
      _OwuiMessageHighlightSweepState();
}

class _OwuiMessageHighlightSweepState extends State<OwuiMessageHighlightSweep>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: widget.totalDuration,
    )..forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: ClipRRect(
        borderRadius: widget.borderRadius,
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, _) {
            final t = _controller.value.clamp(0.0, 1.0);

            final inW = widget.expandDuration.inMilliseconds.toDouble();
            final holdW = widget.holdDuration.inMilliseconds.toDouble();
            final outW = widget.fadeOutDuration.inMilliseconds.toDouble();
            final totalW = (inW + holdW + outW).clamp(1.0, double.infinity);

            final p1End = inW / totalW;
            final p2End = (inW + holdW) / totalW;

            double opacity;
            if (t <= p1End) {
              final local = (t / p1End).clamp(0.0, 1.0);
              opacity = widget.maxOpacity * widget.curve.transform(local);
            } else if (t <= p2End) {
              opacity = widget.maxOpacity;
            } else {
              final local = ((t - p2End) / (1 - p2End)).clamp(0.0, 1.0);
              opacity = widget.maxOpacity * (1 - Curves.easeInCubic.transform(local));
            }

            if (opacity <= 0.001) return const SizedBox.expand();

            return ColoredBox(
              color: widget.color.withValues(alpha: opacity),
              child: const SizedBox.expand(),
            );
          },
        ),
      ),
    );
  }
}
