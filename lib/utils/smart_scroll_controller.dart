import 'dart:async';
import 'package:flutter/material.dart';
import 'package:scrollable_positioned_list/scrollable_positioned_list.dart';

class SmartScrollController {
  final ItemScrollController scrollController;
  final ItemPositionsListener positionsListener;
  
  final double lockThreshold;
  final double unlockThreshold;
  final bool enableDebugLog;
  
  bool _isLocked = true;
  double _lastScrollPosition = 0;
  int _lastMessageCount = 0;
  Timer? _scrollThrottleTimer;
  bool _canScroll = true;
  
  SmartScrollController({
    required this.scrollController,
    required this.positionsListener,
    this.lockThreshold = 10.0,
    this.unlockThreshold = 50.0,
    this.enableDebugLog = false,
  }) {
    positionsListener.itemPositions.addListener(_onScrollChanged);
  }
  
  bool get isLocked => _isLocked;
  
  void _onScrollChanged() {
    final positions = positionsListener.itemPositions.value;
    if (positions.isEmpty) return;
    
    final lastPosition = positions.last;
    final currentScrollPosition = lastPosition.itemTrailingEdge;
    
    final scrollDelta = currentScrollPosition - _lastScrollPosition;
    
    if (scrollDelta < 0 && scrollDelta.abs() > (unlockThreshold / 1000)) {
      if (_isLocked) {
        _isLocked = false;
        if (enableDebugLog) {
          debugPrint('SmartScroll: Unlocked (scrolled up ${scrollDelta.abs() * 1000}px)');
        }
      }
    }
    
    final distanceFromBottom = 1.0 - currentScrollPosition;
    if (distanceFromBottom < (lockThreshold / 1000)) {
      if (!_isLocked) {
        _isLocked = true;
        if (enableDebugLog) {
          debugPrint('SmartScroll: Locked (near bottom ${distanceFromBottom * 1000}px)');
        }
      }
    }
    
    _lastScrollPosition = currentScrollPosition;
  }
  
  Future<void> autoScrollToBottom({
    required int messageCount,
    bool smooth = true,
  }) async {
    if (!_isLocked) {
      if (enableDebugLog) {
        debugPrint('SmartScroll: Skip auto-scroll (unlocked)');
      }
      return;
    }
    
    if (!_canScroll) {
      if (enableDebugLog) {
        debugPrint('SmartScroll: Skip auto-scroll (throttled)');
      }
      return;
    }
    
    final hasNewContent = messageCount > _lastMessageCount;
    if (!hasNewContent && messageCount == _lastMessageCount) {
      return;
    }
    
    _lastMessageCount = messageCount;
    
    if (!scrollController.isAttached || messageCount == 0) return;
    
    final lastIndex = messageCount - 1;
    
    if (enableDebugLog) {
      debugPrint('SmartScroll: Auto-scroll to index $lastIndex (total: $messageCount)');
    }
    
    _canScroll = false;
    _scrollThrottleTimer?.cancel();
    _scrollThrottleTimer = Timer(const Duration(milliseconds: 100), () {
      _canScroll = true;
    });
    
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!scrollController.isAttached) return;
      
      if (smooth) {
        scrollController.scrollTo(
          index: lastIndex,
          duration: const Duration(milliseconds: 150),
          curve: Curves.easeOutQuad,
          alignment: 1.0,
        );
      } else {
        scrollController.jumpTo(index: lastIndex);
      }
    });
  }
  
  Future<void> scrollToBottom({bool smooth = true, int? messageCount}) async {
    _isLocked = true;
    
    // 🔥 修复：允许外部传入最新的消息数量，确保索引正确
    if (messageCount != null) {
      _lastMessageCount = messageCount;
    }
    
    await Future.delayed(Duration.zero);
    
    if (scrollController.isAttached && _lastMessageCount > 0) {
      final lastIndex = _lastMessageCount - 1;
      
      if (enableDebugLog) {
        debugPrint('SmartScroll: scrollToBottom to index $lastIndex (messageCount: $_lastMessageCount)');
      }
      
      scrollController.scrollTo(
        index: lastIndex,
        duration: smooth ? const Duration(milliseconds: 300) : Duration.zero,
        curve: Curves.easeInOutCubic,
        alignment: 1.0,
      );
    }
  }
  
  void dispose() {
    _scrollThrottleTimer?.cancel();
    positionsListener.itemPositions.removeListener(_onScrollChanged);
  }
}
