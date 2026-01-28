import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

/// A mixin for State classes that provides keyboard height detection and notification.
///
/// Automatically handles listening to `WidgetsBinding` for metrics changes.
///
  /// MODIFIED: Removed 100ms debounce to enable immediate response during keyboard animation.
  /// Uses per-frame scheduling to avoid redundant calls within the same frame.
  /// We schedule at frame start to keep scroll updates in sync with keyboard frames.
mixin KeyboardMixin<T extends StatefulWidget>
    on State<T>, WidgetsBindingObserver {
  double _previousKeyboardHeight = 0;
  double _initialSafeArea = 0;
  bool _initialized = false;
  bool _frameScheduled = false;

  /// Abstract method to be implemented by the consuming State.
  /// Called when the keyboard height changes.
  /// The provided [height] is adjusted for the initial bottom safe area.
  void onKeyboardHeightChanged(double height);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_initialized) {
      _initialSafeArea = MediaQuery.of(context).padding.bottom;
      _initialized = true;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeMetrics() {
    super.didChangeMetrics();
    if (!mounted || _frameScheduled) return;

    _frameScheduled = true;
    SchedulerBinding.instance.scheduleFrameCallback((_) {
      _frameScheduled = false;
      if (!mounted) return;

      final view = View.of(context);
      final keyboardHeight = view.viewInsets.bottom;
      final pixelRatio = MediaQuery.of(context).devicePixelRatio;
      final adjustedHeight = max(keyboardHeight / pixelRatio - _initialSafeArea, 0.0);

      // Only notify if height actually changed significantly
      if ((adjustedHeight - _previousKeyboardHeight).abs() < 0.5) return;
      _previousKeyboardHeight = adjustedHeight;

      onKeyboardHeightChanged(adjustedHeight);
    });
  }
}
