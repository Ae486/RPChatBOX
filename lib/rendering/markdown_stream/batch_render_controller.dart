import 'dart:async';
import 'package:flutter/scheduler.dart';

/// 批次渲染配置
class BatchRenderOptions {
  /// 初始批次大小（立即渲染）
  final int initialBatchSize;

  /// 后续每批大小
  final int batchSize;

  /// 批次之间的延迟
  final Duration batchDelay;

  /// 每批预算时间（超过则缩减后续批次）
  final Duration batchBudget;

  /// 最大存活节点数（虚拟化）
  final int maxLiveNodes;

  /// 视口缓冲区大小
  final int liveNodeBuffer;

  const BatchRenderOptions({
    this.initialBatchSize = 40,
    this.batchSize = 80,
    this.batchDelay = const Duration(milliseconds: 16),
    this.batchBudget = const Duration(milliseconds: 6),
    this.maxLiveNodes = 320,
    this.liveNodeBuffer = 60,
  });

  /// 默认配置
  static const defaultOptions = BatchRenderOptions();

  /// 快速渲染配置（更大批次）
  static const fastOptions = BatchRenderOptions(
    initialBatchSize: 80,
    batchSize: 160,
    batchDelay: Duration(milliseconds: 8),
  );

  /// 节能配置（更小批次，更长延迟）
  static const conservativeOptions = BatchRenderOptions(
    initialBatchSize: 20,
    batchSize: 40,
    batchDelay: Duration(milliseconds: 32),
  );
}

/// 批次渲染状态
enum BatchRenderState {
  /// 空闲
  idle,
  /// 正在渲染初始批次
  renderingInitial,
  /// 正在渲染后续批次
  renderingBatch,
  /// 已完成
  completed,
}

/// 批次渲染控制器
/// 
/// 参考 markstream-vue 的 batchRendering 机制实现
/// 用于控制大量节点的分批渲染，避免一次性渲染导致卡顿
class BatchRenderController {
  final BatchRenderOptions options;

  /// 当前状态
  BatchRenderState _state = BatchRenderState.idle;
  BatchRenderState get state => _state;

  /// 已渲染节点数
  int _renderedCount = 0;
  int get renderedCount => _renderedCount;

  /// 总节点数
  int _totalCount = 0;
  int get totalCount => _totalCount;

  /// 是否已取消
  bool _cancelled = false;

  /// 状态变化回调
  final void Function(int renderedCount, int totalCount)? onProgress;
  final void Function()? onComplete;

  Timer? _batchTimer;

  BatchRenderController({
    this.options = const BatchRenderOptions(),
    this.onProgress,
    this.onComplete,
  });

  /// 开始批次渲染
  /// 
  /// [totalItems] 总节点数
  /// [renderBatch] 渲染指定范围的回调 (startIndex, endIndex)
  void start({
    required int totalItems,
    required void Function(int start, int end) renderBatch,
  }) {
    _cancelled = false;
    _totalCount = totalItems;
    _renderedCount = 0;
    _state = BatchRenderState.renderingInitial;

    // 立即渲染初始批次
    final initialEnd = totalItems < options.initialBatchSize 
        ? totalItems 
        : options.initialBatchSize;
    
    renderBatch(0, initialEnd);
    _renderedCount = initialEnd;
    onProgress?.call(_renderedCount, _totalCount);

    if (_renderedCount >= _totalCount) {
      _complete();
      return;
    }

    // 调度后续批次
    _state = BatchRenderState.renderingBatch;
    _scheduleNextBatch(renderBatch);
  }

  void _scheduleNextBatch(void Function(int start, int end) renderBatch) {
    if (_cancelled) return;

    _batchTimer?.cancel();
    _batchTimer = Timer(options.batchDelay, () {
      if (_cancelled) return;

      SchedulerBinding.instance.addPostFrameCallback((_) {
        if (_cancelled) return;

        final stopwatch = Stopwatch()..start();
        
        final start = _renderedCount;
        var end = start + options.batchSize;
        if (end > _totalCount) end = _totalCount;

        renderBatch(start, end);
        _renderedCount = end;

        stopwatch.stop();

        onProgress?.call(_renderedCount, _totalCount);

        if (_renderedCount >= _totalCount) {
          _complete();
          return;
        }

        // 如果超预算，可以动态调整（这里简化处理）
        _scheduleNextBatch(renderBatch);
      });
    });
  }

  void _complete() {
    _state = BatchRenderState.completed;
    onComplete?.call();
  }

  /// 取消批次渲染
  void cancel() {
    _cancelled = true;
    _batchTimer?.cancel();
    _batchTimer = null;
    _state = BatchRenderState.idle;
  }

  /// 重置控制器
  void reset() {
    cancel();
    _renderedCount = 0;
    _totalCount = 0;
  }

  /// 释放资源
  void dispose() {
    cancel();
  }

  /// 计算应该渲染的节点范围（用于虚拟化）
  /// 
  /// [focusIndex] 当前焦点节点索引（通常是视口中心）
  /// [totalItems] 总节点数
  /// 返回 (startIndex, endIndex) 应该保持渲染的范围
  ({int start, int end}) calculateLiveRange(int focusIndex, int totalItems) {
    if (totalItems <= options.maxLiveNodes) {
      return (start: 0, end: totalItems);
    }

    final halfLive = options.maxLiveNodes ~/ 2;
    var start = focusIndex - halfLive;
    var end = focusIndex + halfLive;

    // 边界调整
    if (start < 0) {
      end -= start;
      start = 0;
    }
    if (end > totalItems) {
      start -= (end - totalItems);
      end = totalItems;
    }
    if (start < 0) start = 0;

    return (start: start, end: end);
  }

  /// 判断节点是否应该被渲染（虚拟化判断）
  bool shouldRenderNode(int index, int focusIndex, int totalItems) {
    final range = calculateLiveRange(focusIndex, totalItems);
    return index >= range.start && index < range.end;
  }
}
