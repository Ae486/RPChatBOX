import 'dart:math';
import 'package:flutter/material.dart';

/// A mixin for State classes that provides keyboard height detection and notification.
///
/// Uses per-frame post-layout scheduling for accurate scroll metrics measurement.
mixin KeyboardMixin<T extends StatefulWidget>
    on State<T>, WidgetsBindingObserver {
  double _previousKeyboardHeight = 0;
  double _initialSafeArea = 0;
  bool _initialized = false;
  bool _frameScheduled = false;

  /// Epsilon for keyboard height change detection (logical pixels).
  static const double kHeightChangeEpsilon = 1.0;

  /// Called when the keyboard height changes.
  /// The provided [height] excludes the bottom safe area.
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
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _frameScheduled = false;
      if (!mounted) return;

      // View.viewInsets.bottom is in physical pixels, convert to logical
      final view = View.of(context);
      final keyboardHeight = view.viewInsets.bottom;
      final pixelRatio = view.devicePixelRatio;
      final adjustedHeight = max(keyboardHeight / pixelRatio - _initialSafeArea, 0.0);

      if ((adjustedHeight - _previousKeyboardHeight).abs() < kHeightChangeEpsilon) return;
      _previousKeyboardHeight = adjustedHeight;

      onKeyboardHeightChanged(adjustedHeight);
    });
  }

  /// Returns the current effective keyboard height (for use in other classes).
  double get currentKeyboardHeight => _previousKeyboardHeight;
}
