part of '../flyer_chat_demo_page.dart';

/// 渲染指标
class _RenderMetrics {
  final String type; // 'stream', 'batch', 'cache-hit', 'latex', 'mermaid'
  final Duration duration;
  final int contentLength;
  final DateTime timestamp;
  final bool success;
  final String? error;

  _RenderMetrics({
    required this.type,
    required this.duration,
    required this.contentLength,
    required this.success,
    this.error,
  }) : timestamp = DateTime.now();
}

/// 性能监控器
/// 
/// 参考 markstream-vue: src/utils/performance-monitor.ts
class _PerformanceMonitor extends ChangeNotifier {
  final List<_RenderMetrics> _metrics = [];
  bool _enabled = false;
  static const int _maxMetrics = 500;

  bool get enabled => _enabled;
  int get metricsCount => _metrics.length;

  void enable() {
    _enabled = true;
    notifyListeners();
  }

  void disable() {
    _enabled = false;
    notifyListeners();
  }

  void toggle() {
    _enabled = !_enabled;
    notifyListeners();
  }

  void recordRender({
    required String type,
    required Duration duration,
    required int contentLength,
    bool success = true,
    String? error,
  }) {
    if (!_enabled) return;

    _metrics.add(_RenderMetrics(
      type: type,
      duration: duration,
      contentLength: contentLength,
      success: success,
      error: error,
    ));

    if (_metrics.length > _maxMetrics) {
      _metrics.removeAt(0);
    }

    notifyListeners();
  }

  /// 获取统计数据
  Map<String, dynamic> getStats() {
    if (_metrics.isEmpty) {
      return {
        'totalRenders': 0,
        'avgDuration': 0.0,
        'recommendation': '数据不足',
      };
    }

    final byType = <String, List<_RenderMetrics>>{};
    for (final m in _metrics) {
      byType.putIfAbsent(m.type, () => []).add(m);
    }

    final totalRenders = _metrics.length;
    final successRate = _metrics.where((m) => m.success).length / totalRenders * 100;

    final avgDuration = _metrics.fold<int>(0, (sum, m) => sum + m.duration.inMicroseconds) / 
                        totalRenders / 1000; // ms

    final typeStats = <String, Map<String, dynamic>>{};
    for (final entry in byType.entries) {
      final list = entry.value;
      final avgMs = list.fold<int>(0, (sum, m) => sum + m.duration.inMicroseconds) / 
                    list.length / 1000;
      typeStats[entry.key] = {
        'count': list.length,
        'avgMs': avgMs.toStringAsFixed(2),
      };
    }

    String recommendation;
    if (avgDuration < 16) {
      recommendation = '✅ 渲染性能优秀 (<16ms)';
    } else if (avgDuration < 33) {
      recommendation = '✅ 渲染性能良好 (<33ms)';
    } else if (avgDuration < 100) {
      recommendation = '⚠️ 渲染略慢，考虑优化';
    } else {
      recommendation = '❌ 渲染过慢，需要优化';
    }

    return {
      'totalRenders': totalRenders,
      'successRate': '${successRate.toStringAsFixed(1)}%',
      'avgDuration': '${avgDuration.toStringAsFixed(2)}ms',
      'typeStats': typeStats,
      'recommendation': recommendation,
    };
  }

  /// 获取最近 N 条指标
  List<_RenderMetrics> getRecentMetrics([int count = 20]) {
    final start = _metrics.length > count ? _metrics.length - count : 0;
    return _metrics.sublist(start);
  }

  void reset() {
    _metrics.clear();
    notifyListeners();
  }
}

/// 性能监控面板
class _PerformancePanel extends StatelessWidget {
  final _PerformanceMonitor monitor;
  final VoidCallback onClose;

  const _PerformancePanel({
    required this.monitor,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: monitor,
      builder: (context, _) {
        final stats = monitor.getStats();
        final recentMetrics = monitor.getRecentMetrics(10);

        return Container(
          margin: const EdgeInsets.all(16),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.grey.shade900.withValues(alpha: 0.95),
            borderRadius: BorderRadius.circular(12),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.3),
                blurRadius: 10,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.analytics, color: Colors.white, size: 20),
                  const SizedBox(width: 8),
                  const Text(
                    '性能监控',
                    style: TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      fontSize: 16,
                    ),
                  ),
                  const Spacer(),
                  Switch(
                    value: monitor.enabled,
                    onChanged: (_) => monitor.toggle(),
                    activeColor: Colors.green,
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white70, size: 18),
                    onPressed: onClose,
                    tooltip: '关闭',
                  ),
                ],
              ),
              const Divider(color: Colors.white24),
              if (!monitor.enabled)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Text(
                    '监控已禁用，点击开关启用',
                    style: TextStyle(color: Colors.white54),
                  ),
                )
              else ...[
                _buildStatRow('总渲染次数', '${stats['totalRenders']}'),
                _buildStatRow('成功率', stats['successRate']),
                _buildStatRow('平均耗时', stats['avgDuration']),
                const SizedBox(height: 8),
                Text(
                  stats['recommendation'],
                  style: const TextStyle(color: Colors.white70, fontSize: 12),
                ),
                if ((stats['typeStats'] as Map).isNotEmpty) ...[
                  const SizedBox(height: 12),
                  const Text(
                    '按类型:',
                    style: TextStyle(color: Colors.white54, fontSize: 11),
                  ),
                  const SizedBox(height: 4),
                  ...(stats['typeStats'] as Map<String, Map<String, dynamic>>)
                      .entries
                      .map((e) => _buildStatRow(
                            e.key,
                            '${e.value['count']}次 (${e.value['avgMs']}ms)',
                          )),
                ],
                if (recentMetrics.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      const Text(
                        '最近渲染:',
                        style: TextStyle(color: Colors.white54, fontSize: 11),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: monitor.reset,
                        child: const Text('重置', style: TextStyle(fontSize: 11)),
                      ),
                    ],
                  ),
                  SizedBox(
                    height: 60,
                    child: ListView.builder(
                      scrollDirection: Axis.horizontal,
                      itemCount: recentMetrics.length,
                      itemBuilder: (context, i) {
                        final m = recentMetrics[i];
                        final ms = m.duration.inMicroseconds / 1000;
                        final color = ms < 16 ? Colors.green : ms < 50 ? Colors.orange : Colors.red;
                        return Padding(
                          padding: const EdgeInsets.only(right: 4),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                width: 20,
                                height: (ms / 2).clamp(4, 40).toDouble(),
                                decoration: BoxDecoration(
                                  color: color,
                                  borderRadius: BorderRadius.circular(2),
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                '${ms.toStringAsFixed(0)}',
                                style: TextStyle(color: color, fontSize: 8),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                  ),
                ],
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _buildStatRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.white70, fontSize: 12)),
          Text(value, style: const TextStyle(color: Colors.white, fontSize: 12)),
        ],
      ),
    );
  }
}
