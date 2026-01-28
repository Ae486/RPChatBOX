/// 空闲检测器
///
/// 检测用户空闲状态，触发后台维护任务
/// POS: Services / Roleplay / Worker / Idle
library;

/// 空闲检测器
class IdleDetector {
  /// 空闲阈值
  final Duration idleThreshold;

  /// 最后交互时间
  DateTime _lastInteraction = DateTime.now();

  /// 是否已启动
  bool _started = false;

  IdleDetector({
    this.idleThreshold = const Duration(seconds: 45),
  });

  /// 记录用户交互
  void recordInteraction() {
    _lastInteraction = DateTime.now();
  }

  /// 是否空闲
  bool get isIdle {
    if (!_started) return false;
    return DateTime.now().difference(_lastInteraction) > idleThreshold;
  }

  /// 空闲持续时间
  Duration get idleDuration => DateTime.now().difference(_lastInteraction);

  /// 启动检测
  void start() {
    _started = true;
    _lastInteraction = DateTime.now();
  }

  /// 停止检测
  void stop() {
    _started = false;
  }

  /// 重置
  void reset() {
    _lastInteraction = DateTime.now();
  }
}
