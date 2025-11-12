import 'dart:async';
import 'package:flutter/foundation.dart';
import '../core/render_cache.dart';

/// 渲染性能监控工具
class PerformanceMonitor {
  static final PerformanceMonitor _instance = PerformanceMonitor._internal();
  factory PerformanceMonitor() => _instance;
  PerformanceMonitor._internal() {
    _startAutoReport();
  }

  final List<_RenderRecord> _records = [];
  static const int maxRecords = 100;
  Timer? _reportTimer;
  int _lastReportedCount = 0;

  /// 记录渲染操作
  void recordRender({
    required String contentType,
    required int contentLength,
    required Duration duration,
    required bool cacheHit,
  }) {
    _records.add(_RenderRecord(
      contentType: contentType,
      contentLength: contentLength,
      duration: duration,
      cacheHit: cacheHit,
      timestamp: DateTime.now(),
    ));

    // 限制记录数量
    if (_records.length > maxRecords) {
      _records.removeAt(0);
    }
  }

  /// 获取性能统计
  Map<String, dynamic> getStats() {
    if (_records.isEmpty) {
      return {
        'totalRecords': 0,
        'avgRenderTime': 0.0,
        'cacheHitRate': 0.0,
        'cacheMissAvgTime': 0.0,
        'cacheHitAvgTime': 0.0,
      };
    }

    final cacheHits = _records.where((r) => r.cacheHit).length;
    final cacheMisses = _records.length - cacheHits;
    
    final cacheHitRecords = _records.where((r) => r.cacheHit);
    final cacheMissRecords = _records.where((r) => !r.cacheHit);

    final avgCacheHitTime = cacheHitRecords.isEmpty
        ? 0.0
        : cacheHitRecords.map((r) => r.duration.inMicroseconds).reduce((a, b) => a + b) /
            cacheHitRecords.length /
            1000; // ms

    final avgCacheMissTime = cacheMissRecords.isEmpty
        ? 0.0
        : cacheMissRecords.map((r) => r.duration.inMicroseconds).reduce((a, b) => a + b) /
            cacheMissRecords.length /
            1000; // ms

    final avgRenderTime = _records.map((r) => r.duration.inMicroseconds).reduce((a, b) => a + b) /
        _records.length /
        1000;

    final cacheStats = RenderCache().getStats();

    return {
      'totalRecords': _records.length,
      'avgRenderTime': avgRenderTime.toStringAsFixed(2),
      'cacheHitRate': cacheStats['hitRate'],
      'cacheMissAvgTime': avgCacheMissTime.toStringAsFixed(2),
      'cacheHitAvgTime': avgCacheHitTime.toStringAsFixed(2),
      'cacheHits': cacheHits,
      'cacheMisses': cacheMisses,
      'cacheSize': cacheStats['size'],
      'speedup': avgCacheMissTime > 0 
          ? '${(avgCacheMissTime / avgCacheHitTime).toStringAsFixed(2)}x'
          : 'N/A',
    };
  }

  /// 打印性能报告
  void printReport() {
    if (kDebugMode) {
      final stats = getStats();
      debugPrint('=== 渲染性能报告 ===');
      debugPrint('总渲染次数: ${stats['totalRecords']}');
      debugPrint('平均渲染时间: ${stats['avgRenderTime']} ms');
      debugPrint('缓存命中率: ${stats['cacheHitRate']}');
      debugPrint('缓存命中平均时间: ${stats['cacheHitAvgTime']} ms');
      debugPrint('缓存未命中平均时间: ${stats['cacheMissAvgTime']} ms');
      debugPrint('性能提升: ${stats['speedup']}');
      debugPrint('缓存使用: ${stats['cacheSize']} 项');
      debugPrint('====================');
    }
  }

  /// 清除记录
  void clear() {
    _records.clear();
    _lastReportedCount = 0;
  }

  /// 启动自动报告（仅在调试模式）
  void _startAutoReport() {
    if (!kDebugMode) return;

    // 每30秒输出一次统计（如果有新数据）
    _reportTimer = Timer.periodic(const Duration(seconds: 30), (timer) {
      if (_records.isEmpty) return;
      
      // 只有在有新的渲染记录时才输出
      if (_records.length > _lastReportedCount) {
        _printSimpleReport();
        _lastReportedCount = _records.length;
      }
    });
  }

  /// 简化的控制台输出
  void _printSimpleReport() {
    if (!kDebugMode) return;
    
    final stats = getStats();
    final cacheStats = RenderCache().getStats();
    
    debugPrint('\n[渲染性能] 渲染${stats['totalRecords']}次 | '
        '缓存命中率${stats['cacheHitRate']} | '
        '平均${stats['avgRenderTime']}ms | '
        '提升${stats['speedup']} | '
        '缓存${cacheStats['size']}/${cacheStats['maxSize']}项');
  }

  /// 释放资源
  void dispose() {
    _reportTimer?.cancel();
    _reportTimer = null;
  }
}

/// 渲染记录
class _RenderRecord {
  final String contentType;
  final int contentLength;
  final Duration duration;
  final bool cacheHit;
  final DateTime timestamp;

  _RenderRecord({
    required this.contentType,
    required this.contentLength,
    required this.duration,
    required this.cacheHit,
    required this.timestamp,
  });
}

/// 性能计时器辅助类
class RenderTimer {
  final Stopwatch _stopwatch = Stopwatch();
  final String contentType;
  final int contentLength;
  bool cacheHit;

  RenderTimer({
    required this.contentType,
    required this.contentLength,
    this.cacheHit = false,
  });

  /// 开始计时
  void start() {
    _stopwatch.start();
  }

  /// 停止计时并记录
  void stop() {
    _stopwatch.stop();
    PerformanceMonitor().recordRender(
      contentType: contentType,
      contentLength: contentLength,
      duration: _stopwatch.elapsed,
      cacheHit: cacheHit,
    );
  }

  /// 标记为缓存命中
  void markCacheHit() {
    cacheHit = true;
  }
}
